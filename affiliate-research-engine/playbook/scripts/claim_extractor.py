#!/usr/bin/env python3
"""
claim_extractor.py
公開記事から「体験の主張」を抜き出し、重複をまとめて確認用の一覧にする。

記事は生成物なので、そこに書かれている体験は**事実とは限らない**。
どれが実体験でどれが生成設定かを人が判定できる形にするのが目的。
**記事は一切修正しない。** 抽出と整理だけをする。

出力:
  workspace/claims/CLAIMS.csv … 人が confirmation 列を埋める
  workspace/claims/CLAIMS.md  … 読む用
"""
import csv
import os
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings()
sys.path.insert(0, str(Path(__file__).parent))
import quality_rules as _q
import wp_audit as _wa

OUT = Path("affiliate-research-engine/playbook/workspace/claims")
# 生成設定の出どころを探す先。ここに同じ数字があれば、記事の外から来ている
SETTING_FILES = [
    Path("affiliate-research-engine/CLAUDE.md"),
    *sorted(Path("affiliate-research-engine/playbook/workspace/drafts").glob("*.md")),
]

# ── 主張の型。type ごとに、拾い方と正規化の仕方が違う ──────────────
PATTERNS = [
    ("スコア", re.compile(r"TOEIC[^。]{0,14}?([0-9]{3})\s*点")),
    ("金額", re.compile(r"([0-9][0-9,\.]*)\s*(万?)円[^。]{0,14}?"
                        r"(?:溶かした|払った|使った|消えた|かかった|無駄)")),
    ("金額", re.compile(r"(?:溶かした|払った|使った|かかった)[^。]{0,10}?"
                        r"([0-9][0-9,\.]*)\s*(万?)円")),
    ("期間", re.compile(r"([0-9]+)\s*(年|ヶ月|か月|日|週間)[^。]{0,14}?"
                        r"(?:続けた|続いた|通った|やった|止まって|停滞|後回し|放置|中断)")),
    ("回数", re.compile(r"([0-9]+)\s*回[^。]{0,14}?"
                        r"(?:登録|受けた|受験|申し込|試した|やめた|挫折)")),
    ("渡航", re.compile(r"(セブ島?|フィリピン|オーストラリア|カナダ|ニュージーランド|"
                        r"イギリス|ハワイ|シンガポール|台湾|韓国)"
                        r"[^。]{0,18}?(?:留学|行った|滞在|渡航|住んで)")),
    ("職歴", re.compile(r"(営業事務|経理|総務|販売|エンジニア|営業職)"
                        r"[^。]{0,14}?(?:として|の私|で働)")),
]


def claim_key(ctype, m):
    """重複をまとめるためのキー。同じ主張は1件にする。"""
    if ctype == "スコア":
        return f"スコア:TOEIC{m.group(1)}点"
    if ctype == "金額":
        n = m.group(1).replace(",", "")
        return f"金額:{n}{'万' if m.group(2) else ''}円"
    if ctype == "期間":
        return f"期間:{m.group(1)}{m.group(2)}"
    if ctype == "回数":
        return f"回数:{m.group(1)}回"
    return f"{ctype}:{m.group(1)}"


def setting_sources(value):
    """CLAUDE.md や下書きに同じ数字があるか。あれば生成設定が出どころ。"""
    hits = []
    num = re.sub(r"[^0-9]", "", value)
    if not num:
        return hits
    for f in SETTING_FILES:
        if not f.exists():
            continue
        try:
            t = f.read_text(encoding="utf-8")
        except Exception:
            continue
        if num in re.sub(r"[,，]", "", t):
            hits.append(f.name)
    return hits[:4]


def ledger_verdict(claim, excerpt):
    """いまの台帳ではどう判定されるか。"""
    e = _q.experience_claims(excerpt)
    if e:
        return e[0]
    if claim.startswith(("スコア", "金額", "期間")):
        return "事実台帳に該当なし（experience_facts.csv が空）"
    return "判定対象外"


NEEDS = {
    "スコア": "TOEIC公式マイページのスコアと受験日",
    "金額": "クレジットカード・銀行の明細",
    "期間": "各サービスの受講履歴、または学習記録",
    "回数": "各サービスのアカウント履歴",
    "渡航": "パスポートの出入国記録",
    "職歴": "職務経歴（本人の申告で足りる）",
}
DIRECTION = {
    "スコア": "事実なら台帳へ。違うなら数字を外すか、読者の例として書き直す",
    "金額": "事実なら台帳へ。違うなら金額を消し、一般的な相場として書き直す",
    "期間": "事実なら台帳へ。違うなら期間を消すか、読者の状況として書き直す",
    "回数": "事実なら台帳へ。違うなら回数を消す",
    "渡航": "事実なら台帳へ。違うなら『調べた』『比較した』へ直す",
    "職歴": "事実なら台帳へ。違うなら職種の断定を外す",
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    posts = _wa.published()
    print(f"公開中 {len(posts)}本から体験の主張を抜き出す\n")

    claims = defaultdict(lambda: {"type": "", "value": "", "posts": [], "excerpts": []})

    for p in posts:
        title = re.sub(r"<[^>]+>", "", p["title"]["rendered"])
        text = _q.strip_tags(p.get("content", {}).get("rendered", ""))
        for ctype, pat in PATTERNS:
            for m in pat.finditer(text):
                key = claim_key(ctype, m)
                c = claims[key]
                c["type"] = ctype
                c["value"] = key.split(":", 1)[1]
                if p["id"] not in [x[0] for x in c["posts"]]:
                    c["posts"].append((p["id"], p.get("link", ""), title))
                ex = text[max(0, m.start() - 40):m.end() + 40].strip()
                if len(c["excerpts"]) < 3:
                    c["excerpts"].append(ex)

    rows = []
    for i, (key, c) in enumerate(
            sorted(claims.items(), key=lambda kv: -len(kv[1]["posts"])), start=1):
        cid = f"C{i:03d}"
        src = setting_sources(c["value"])
        rows.append({
            "claim_id": cid,
            "claim": key.split(":", 1)[1],
            "type": c["type"],
            "value": c["value"],
            "posts": len(c["posts"]),
            "post_ids": " ".join(str(x[0]) for x in c["posts"][:12]),
            "urls": " ".join(x[1] for x in c["posts"][:4]),
            "excerpt": c["excerpts"][0][:140] if c["excerpts"] else "",
            "setting_source": " ".join(src) or "（設定ファイルに該当なし）",
            "ledger": ledger_verdict(key, c["excerpts"][0] if c["excerpts"] else ""),
            "needs": NEEDS.get(c["type"], ""),
            "direction": DIRECTION.get(c["type"], ""),
            "confirmation": "",     # ← ここを人が埋める
        })

    with open(OUT / "CLAIMS.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["claim_id"])
        w.writeheader()
        w.writerows(rows)

    L = [f"# 体験主張の確認一覧 {date.today().isoformat()}\n\n",
         f"公開中 {len(posts)}本 / 一意な主張 **{len(rows)}件**\n\n",
         "**記事は一切修正していない。** 抽出と重複排除だけ。\n\n",
         "`CLAIMS.csv` の `confirmation` 列に、次のどれかを書いてください。\n\n",
         "| 値 | 意味 |\n|---|---|\n",
         "| `verified` | 実体験として事実 |\n",
         "| `partially_verified` | 大筋は事実だが数字・期間の修正が必要 |\n",
         "| `fictional` | 生成設定であり事実ではない |\n",
         "| `unknown` | 記録の確認が必要 |\n\n---\n\n"]

    for r in rows:
        L.append(f"## {r['claim_id']} {r['claim']}（{r['type']}）\n\n")
        L.append(f"- **登場記事数**: {r['posts']}本（ID: {r['post_ids']}）\n")
        for pid, url, t in claims[f"{r['type']}:{r['claim']}"]["posts"][:6]:
            L.append(f"  - [{pid}] {t[:38]} {url}\n")
        L.append(f"- **該当箇所**: …{r['excerpt']}…\n")
        L.append(f"- **設定ファイル上の出どころ**: {r['setting_source']}\n")
        L.append(f"- **現在の台帳判定**: {r['ledger']}\n")
        L.append(f"- **事実確認に必要なもの**: {r['needs']}\n")
        L.append(f"- **修正の方向性**: {r['direction']}\n")
        L.append(f"- **confirmation**: （未記入）\n\n")

    (OUT / "CLAIMS.md").write_text("".join(L), encoding="utf-8")
    print(f"一意な主張 {len(rows)}件 → {OUT/'CLAIMS.csv'} / {OUT/'CLAIMS.md'}")
    for r in rows[:20]:
        print(f"  {r['claim_id']} {r['posts']:>2}本  {r['claim']:<14} {r['setting_source'][:30]}")


if __name__ == "__main__":
    main()
