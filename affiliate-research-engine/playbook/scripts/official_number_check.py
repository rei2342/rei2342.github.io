#!/usr/bin/env python3
"""
official_number_check.py
記事に書いた公式の数値を、**引用元ページを実際に取りに行って照合する。**

ゲートは「出典URLと確認日が書いてあるか」しか見ていない。
そのURLに本当にその数字が載っているかは、これまで誰も確認していなかった
（2026-08-08にGENERATION_TEST.mdへ限界として書いた宿題）。

やること:
  1. 公開記事から「URLを含む文」を取り出す
  2. その文の中の数値・仕様の語を主張として抜く
  3. URLを取得して、主張がページ本文に出てくるかを照合
  4. 一致 / 不一致 / 取得できず を1行ずつ出す

**不一致と取得不能は自動で直さない。** 一覧に出して人が判断する。

  python official_number_check.py
出力: workspace/claims/NUMBER_MATCH.md / .csv
"""
import csv
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings()
sys.path.insert(0, str(Path(__file__).parent))
import quality_rules as _q
import wp_audit as _wa

OUT = Path("affiliate-research-engine/playbook/workspace/claims")
JST = timezone(timedelta(hours=9))
UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) "
                     "Chrome/124.0 Safari/537.36")}

# 照合する主張の型。ラベルは報告用
CLAIM_PATTERNS = [
    ("金額", re.compile(r"月額?\s*[0-9][0-9,]*\s*円|[0-9][0-9,]*\s*円")),
    ("無料期間", re.compile(r"[0-9]+\s*(?:日間|日|週間|ヶ月|か月|カ月)")),
    ("体験回数", re.compile(r"[0-9]+\s*回")),
    ("対象人数", re.compile(r"[0-9][0-9,]*\s*(?:名|人)")),
    ("年齢", re.compile(r"[0-9]{1,2}\s*歳")),
    ("手数料", re.compile(r"手数料\s*[0-9][0-9,]*\s*円|手数料\s*0\s*円")),
    ("仕様", re.compile(r"無制限|予約不要|回数制限なし|使い放題|完全オンライン")),
    # 「の新日常英会話コース」のように直前の助詞まで取らないようにする
    ("プラン名", re.compile(
        r"(?<![のなをにへとがはもや])"
        r"[ァ-ヶA-Za-z一-龥][ぁ-んァ-ヶ一-龥A-Za-z0-9・ー]{1,14}(?:プラン|コース)")),
    ("キャンペーン", re.compile(r"キャンペーン|初月|今だけ|半額|割引")),
    ("認定", re.compile(r"正式認定校|認定校|公認")),
]

URL_RE = re.compile(r"https?://[^\s<>\"）)」、。]+")
_CACHE = {}


def fetch(url):
    if url in _CACHE:
        return _CACHE[url]
    try:
        r = requests.get(url, headers=UA, timeout=45, verify=False,
                         allow_redirects=True)
        v = ({"text": re.sub(r"\s+", " ", _q.strip_tags(r.text)),
              "final": r.url, "http": r.status_code}
             if r.status_code == 200 else
             {"error": f"HTTP {r.status_code}", "final": r.url})
    except Exception as e:
        v = {"error": f"{type(e).__name__}"}
    _CACHE[url] = v
    return v


def canon(s):
    """全角・カンマ・空白の揺れを吸収して比べる。"""
    s = s.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    return re.sub(r"[,\s　]", "", s)


def _suffix_hit(need, hay, least=5):
    """末尾から詰めた部分文字列がページにあれば、それを返す。"""
    for i in range(len(need) - least + 1):
        tail = need[i:]
        if tail in hay:
            return tail
    return ""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    posts = _wa.published()
    print(f"公開記事 {len(posts)}本")

    rows = []
    for p in posts:
        pid = p["id"]
        html = p.get("content", {}).get("rendered", "")
        # 「公式情報」の段落だけを見る。地の文の数字は対象外
        for m in re.finditer(r"<p>(.*?)</p>", html, re.DOTALL):
            para = m.group(1)
            urls = URL_RE.findall(re.sub(r"&#0?38;", "&", para))
            urls = [u for u in urls
                    if "sakura-eigo.com" not in u
                    and "moshimo.com" not in u and "a8.net" not in u]
            if not urls:
                continue
            text = _q.strip_tags(para)
            # 「2026年8月8日時点」の「8日」を無料期間として拾っていた。
            # 確認日は主張ではないので、照合の前に外す
            text_for_claims = re.sub(
                r"20[0-9]{2}\s*年\s*[0-9]{1,2}\s*月\s*[0-9]{1,2}\s*日"
                r"(?:時点)?", " ", text)
            for label, rx in CLAIM_PATTERNS:
                for hit in set(rx.findall(text_for_claims)):
                    rows.append({"post_id": pid, "kind": label,
                                 "claim": hit, "url": urls[0],
                                 "sentence": text[:200]})

    print(f"照合する主張 {len(rows)}件 / URL {len(set(r['url'] for r in rows))}件")

    for r in rows:
        page = fetch(r["url"])
        if page.get("error"):
            r["page_value"] = ""
            r["match"] = "取得できず"
            r["note"] = page["error"]
            continue
        hay = canon(page["text"])
        need = canon(r["claim"])
        if need in hay:
            r["match"] = "一致"
            r["page_value"] = r["claim"]
            r["note"] = ""
        elif r["kind"] == "プラン名" and _suffix_hit(need, hay):
            # 日本語は語の切れ目が無いので、抜き出しが語の途中から
            # 始まることがある（「リENGLISHの新日常英会話コース」）。
            # 末尾から詰めて、実在する名前で一致するかを見る
            r["match"] = "一致"
            r["page_value"] = _suffix_hit(need, hay)
            r["note"] = "抜き出しが語の途中から始まっていた。末尾で一致"
        else:
            # 数字だけ抜いて、単位違いを見る（7日間 と 7日 など）
            num = re.sub(r"[^0-9]", "", need)
            r["page_value"] = ""
            if num and num in hay:
                r["match"] = "数値のみ一致"
                r["note"] = "単位や表記が違う可能性。人が見る"
            else:
                r["match"] = "不一致"
                r["note"] = "引用元にこの値が見つからない"
        r["checked_at"] = stamp

    order = {"不一致": 0, "取得できず": 1, "数値のみ一致": 2, "一致": 3}
    rows.sort(key=lambda r: (order.get(r["match"], 9), str(r["post_id"])))

    cnt = {k: sum(1 for r in rows if r["match"] == k) for k in order}
    L = [f"# 公式数値の内容照合 {stamp}\n\n",
         "ゲートは「出典URLと確認日が書いてあるか」しか見ていない。\n"
         "**そのURLに本当にその値が載っているか**をここで照合する。\n\n",
         "| 判定 | 件数 | 扱い |\n|---|---|---|\n",
         f"| 不一致 | {cnt['不一致']} | **中立化するか保留にする。自動で直さない** |\n",
         f"| 取得できず | {cnt['取得できず']} | **保留。** 引用元が開けないので確認できない |\n",
         f"| 数値のみ一致 | {cnt['数値のみ一致']} | 単位や表記の違い。人が見る |\n",
         f"| 一致 | {cnt['一致']} | そのままでよい |\n\n",
         "---\n\n| 記事 | 種類 | 記事の値 | 引用元 | 判定 | 備考 | 元文 |\n"
         "|---|---|---|---|---|---|---|\n"]
    for r in rows:
        mark = {"一致": "✅", "数値のみ一致": "⚠️",
                "不一致": "❌", "取得できず": "⏸"}[r["match"]]
        L.append(f"| {r['post_id']} | {r['kind']} | `{r['claim']}` | "
                 f"{r['url'][:52]} | {mark} {r['match']} | {r['note']} | "
                 f"{r['sentence'][:80].replace('|', '｜')} |\n")

    if rows:
        with open(OUT / "NUMBER_MATCH.csv", "w", encoding="utf-8",
                  newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    (OUT / "NUMBER_MATCH.md").write_text("".join(L), encoding="utf-8")
    for k in order:
        print(f"  {k}: {cnt[k]}")
    print(f"\n{len(rows)}件 → NUMBER_MATCH.md")


if __name__ == "__main__":
    main()
