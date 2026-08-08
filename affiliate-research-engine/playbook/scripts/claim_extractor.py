#!/usr/bin/env python3
"""
claim_extractor.py
公開記事から「体験の主張」を**命題単位**で抜き出し、重複をまとめる。

単語や数値で束ねると、別の主張が混ざる。
「フィリピンへ留学した」「フィリピン留学の費用を調べた」
「フィリピンでは英語が公用語」は、同じ「フィリピン」でも全部ちがう。

そこで 主語＋行動／状態＋対象＋数値 の単位で切り出す。
**記事は一切修正しない。** 抽出と整理だけをする。

判定は文の形から機械的に推測しているだけで、完全ではない。
人が元の文を読んで確かめられるよう、必ず原文と前後の文脈を残す。

出力:
  workspace/claims/CLAIMS.csv … 人が confirmation 列を埋める
  workspace/claims/CLAIMS.md  … 読む用（上位から詳細）
"""
import csv
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
SETTING_FILES = [
    Path("affiliate-research-engine/CLAUDE.md"),
    *sorted(Path("affiliate-research-engine/playbook/workspace/drafts").glob("*.md")),
]
TOP = int(__import__("os").environ.get("TOP", "10"))

# ── 行動・状態。どれに当たるかで「体験の主張」かが決まる ──────────────
# 体験: 本人が実際にやったと読める
ACT_EXPERIENCE = {
    "留学した": r"留学(?:し|に行っ|して)", "渡航した": r"渡航し|現地に行っ",
    "通った": r"通っ", "使った": r"使っ(?:た|て)", "試した": r"試し",
    "続けた": r"続け(?:た|られ)", "やめた": r"やめ(?:た|て)|挫折し|중断",
    "受けた": r"受け(?:た|て)", "受験した": r"受験し",
    "登録した": r"登録し|申し込(?:んだ|み)", "払った": r"払っ|支払っ",
    "溶かした": r"溶かし|無駄にし|無駄にし",
    "後回しにした": r"後回しに(?:し|してき)", "止まっていた": r"止まっ|停滞し|動かなかっ",
    "働いている": r"(?:として|で)働(?:い|く)|の仕事をし",
}
# 調査: 調べただけ。体験ではない
ACT_RESEARCH = {
    "調べた": r"調べ", "比較した": r"比較し|比べ", "候補にした": r"候補に(?:し|入れ)",
    "見た": r"(?:サイトを|公式を)見", "問い合わせた": r"問い合わせ",
    "検索した": r"検索し", "読んだ": r"(?:記事を|口コミを)読",
}
# 一般論・第三者。さくらの主張ではない
GENERAL_MARK = r"と言われ|一般的に|多くの人|人によって|とされ|らしい|そうだ|だろう|かもしれない"

SUBJ_SELF = r"私|自分|僕"
SUBJ_READER = r"あなた|読者|みなさん"

# 対象（何について言っているか）
TARGETS = [
    ("フィリピン", r"フィリピン"), ("セブ島", r"セブ島?"),
    ("オーストラリア", r"オーストラリア|豪州"), ("カナダ", r"カナダ"),
    ("ニュージーランド", r"ニュージーランド"), ("シンガポール", r"シンガポール"),
    ("イギリス", r"イギリス|英国"), ("台湾", r"台湾"), ("韓国", r"韓国"),
    ("ハワイ", r"ハワイ"), ("国内留学", r"国内留学"),
    ("英語学習", r"英語(?:学習|の勉強|を勉強)"), ("英語", r"英語"),
    ("TOEIC", r"TOEIC"), ("ワーホリ", r"ワーホリ|ワーキングホリデー"),
    ("オンライン英会話", r"オンライン英会話"), ("英会話スクール", r"(?:英会話)?スクール"),
    ("英語コーチング", r"英語コーチング|コーチング"),
    ("営業事務", r"営業事務"), ("仕事の英語", r"仕事で英語|会議|議事録|電話対応"),
]
for _n in _q.SERVICE_NAMES:
    TARGETS.insert(0, (_n, re.escape(_n)))

NUM_RE = re.compile(r"([0-9][0-9,\.]*)\s*(年間|年|ヶ月|か月|カ月|週間|日間|日|時間|分|"
                    r"回|点|万円|円|コマ|本|ページ)")

NEEDS = {
    "留学した": "パスポートの出入国記録", "渡航した": "パスポートの出入国記録",
    "受験した": "TOEIC公式マイページのスコアと受験日",
    "払った": "クレジットカード・銀行の明細", "溶かした": "クレジットカード・銀行の明細",
    "使った": "サービスのアカウント履歴", "続けた": "サービスのアカウント履歴",
    "通った": "受講記録・領収書", "受けた": "サービスのアカウント履歴",
    "登録した": "サービスのアカウント履歴", "やめた": "サービスのアカウント履歴",
    "働いている": "職務経歴（本人の申告で足りる）",
    "後回しにした": "本人の記憶で足りる", "止まっていた": "TOEIC公式マイページ",
}


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[。？！\n])", text) if s.strip()]


def parse(sent):
    """1文から命題を取り出す。取れなければ None。"""
    if re.search(GENERAL_MARK, sent):
        kind = "一般論"
    else:
        kind = None

    act = act_type = None
    for name, pat in ACT_EXPERIENCE.items():
        if re.search(pat, sent):
            act, act_type = name, "体験"
            break
    if not act:
        for name, pat in ACT_RESEARCH.items():
            if re.search(pat, sent):
                act, act_type = name, "調査"
                break
    if not act:
        return None

    target = next((n for n, p in TARGETS if re.search(p, sent)), None)
    if not target:
        return None

    m = NUM_RE.search(sent)
    value = f"{m.group(1)}{m.group(2)}" if m else ""

    if re.search(SUBJ_READER, sent):
        subj = "読者"
    elif re.search(SUBJ_SELF, sent):
        subj = "さくら"
    elif kind == "一般論":
        subj = "第三者"
    else:
        # 主語が書かれていない日本語は多い。書き手の行為と読むのが自然。
        # 一般論の印がある文だけ第三者にする（上で判定済み）
        subj = "さくら"

    if re.search(r"(?:する|します|したい|予定|つもり|だろう)$", sent.rstrip("。")):
        tense = "未来"
    elif re.search(r"(?:た|だ|ていた|ている)[。、]?$", sent.rstrip("。")) or "し" in act:
        tense = "過去"
    else:
        tense = "現在"

    is_exp = (subj == "さくら" and act_type == "体験" and tense != "未来"
              and kind != "一般論")

    claim = f"{target}を{value}{act}" if value else f"{target}を{act}"
    if act in ("留学した", "渡航した", "働いている"):
        claim = f"{target}へ{act}" if act != "働いている" else f"{target}として{act}"
        if value:
            claim = f"{target}へ{value}{act}"
    return {
        "claim": claim, "subject": subj, "act": act, "act_type": act_type,
        "target": target, "value": value, "tense": tense,
        "is_experience": "yes" if is_exp else "no", "sentence": sent[:200],
    }


def setting_hit(prop):
    """設定ファイルに、同じ対象と数値が出てくるか。文字列でも照合する。"""
    hits = []
    for f in SETTING_FILES:
        if not f.exists():
            continue
        try:
            t = re.sub(r"[,，]", "", f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if prop["target"] not in t:
            continue
        num = re.sub(r"[^0-9]", "", prop["value"])
        if num and num not in t:
            continue
        hits.append(f.name)
    return hits[:4]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    posts = _wa.published()
    print(f"公開中 {len(posts)}本から命題を抜き出す\n")

    props = defaultdict(lambda: {"rows": [], "posts": []})
    for p in posts:
        title = re.sub(r"<[^>]+>", "", p["title"]["rendered"])
        text = _q.strip_tags(p.get("content", {}).get("rendered", ""))
        ss = sentences(text)
        for i, sent in enumerate(ss):
            pr = parse(sent)
            if not pr:
                continue
            key = pr["claim"]
            ctx = " ".join(ss[max(0, i - 1):i + 2])[:260]
            props[key]["rows"].append({**pr, "context": ctx,
                                       "post_id": p["id"], "url": p.get("link", ""),
                                       "title": title})
            if p["id"] not in props[key]["posts"]:
                props[key]["posts"].append(p["id"])

    ordered = sorted(props.items(), key=lambda kv: -len(kv[1]["posts"]))
    rows = []
    for i, (claim, d) in enumerate(ordered, start=1):
        r0 = d["rows"][0]
        rows.append({
            "claim_id": f"C{i:03d}", "claim": claim,
            "subject": r0["subject"], "act": r0["act"], "act_type": r0["act_type"],
            "target": r0["target"], "value": r0["value"], "tense": r0["tense"],
            "is_experience": r0["is_experience"],
            "posts": len(d["posts"]),
            "post_ids": " ".join(str(x) for x in d["posts"][:12]),
            "url": r0["url"], "sentence": r0["sentence"], "context": r0["context"],
            "setting_source": " ".join(setting_hit(r0)) or "（該当なし）",
            "needs": NEEDS.get(r0["act"], "本人の確認"),
            "confirmation": "",
        })

    with open(OUT / "CLAIMS.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["claim_id"])
        w.writeheader()
        w.writerows(rows)

    exp = [r for r in rows if r["is_experience"] == "yes"]
    L = [f"# 体験主張の確認一覧（命題単位） {date.today().isoformat()}\n\n",
         f"公開中 {len(posts)}本 / 命題 **{len(rows)}件**"
         f"（うち一人称の体験主張 **{len(exp)}件**）\n\n",
         "**記事は一切修正していない。**\n\n",
         "判定は文の形からの推測。**必ず原文を読んで確かめてから** "
         "`confirmation` を入れてください（verified / partially_verified / "
         "fictional / unknown）。\n\n---\n\n"]

    for r in rows[:TOP]:
        L.append(f"## {r['claim_id']} {r['claim']}\n\n")
        L.append(f"| 項目 | 値 |\n|---|---|\n")
        L.append(f"| 主語 | {r['subject']} |\n| 行動・状態 | {r['act']}（{r['act_type']}） |\n")
        L.append(f"| 対象 | {r['target']} |\n| 数値と単位 | {r['value'] or '—'} |\n")
        L.append(f"| 時制 | {r['tense']} |\n| 一人称の体験主張か | **{r['is_experience']}** |\n")
        L.append(f"| 登場記事数 | {r['posts']}本（{r['post_ids']}） |\n")
        L.append(f"| 設定ファイルの一致 | {r['setting_source']} |\n")
        L.append(f"| 事実確認に必要なもの | {r['needs']} |\n\n")
        L.append(f"**元の文章**\n\n> {r['sentence']}\n\n")
        L.append(f"**前後の文脈**\n\n> {r['context']}\n\n")
        L.append(f"**記事**: {r['url']}\n\n**confirmation**: （未記入）\n\n---\n\n")

    (OUT / "CLAIMS.md").write_text("".join(L), encoding="utf-8")
    print(f"命題 {len(rows)}件（体験主張 {len(exp)}件）")
    print(f"{'ID':6}{'記事':>4} {'体験':<5}{'主語':<5}{'時制':<5}{'命題'}")
    for r in rows[:TOP + 10]:
        print(f"{r['claim_id']:6}{r['posts']:>4} {r['is_experience']:<5}"
              f"{r['subject']:<5}{r['tense']:<5}{r['claim']}")


if __name__ == "__main__":
    main()
