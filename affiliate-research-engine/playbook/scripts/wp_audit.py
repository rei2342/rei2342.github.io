#!/usr/bin/env python3
"""
wp_audit.py
公開中の記事を全部検査する。

公開時のゲート（wp_publisher.py）は投稿の瞬間しか見ないので、
あとから壊れたものを捕まえられない。
本文を書き換えてCTAが消える、案件の判定が変わる、
料金記事が日付なしのまま古くなる、といった劣化は
定期的に全部を見ないと気づけない。

レイチームの publish_audit.py の発想を取り込んだもの。
"""
import os
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings()

WP_BASE = "https://sakura-eigo.com/wp-json/wp/v2"
WP_USER = "rei.00pt2342@gmail.com"
WP_PASS = os.environ.get("WP_APP_PASSWORD", "")
MIN_CHARS = int(os.environ.get("MIN_CHARS", "3000"))
OUT = Path("affiliate-research-engine/playbook/workspace/site")

UNCATEGORIZED_ID = 1
SKIP_MARKS = ("【Threads用】", "【メモ】", "【社内")


def published():
    posts, page = [], 1
    while True:
        r = requests.get(f"{WP_BASE}/posts", auth=(WP_USER, WP_PASS),
                         params={"per_page": 100, "page": page, "status": "publish",
                                 "_fields": "id,title,content,link,categories,featured_media"},
                         headers={"User-Agent": "Mozilla/5.0"},
                         verify=False, timeout=40)
        if r.status_code != 200:
            break
        b = r.json()
        if not b:
            break
        posts += b
        if len(b) < 100:
            break
        page += 1
    return posts


def audit(post):
    """公開中の記事として成立しているかを見る。問題があれば理由を返す。"""
    issues = []
    title = post["title"]["rendered"]
    body = post.get("content", {}).get("rendered", "")
    # タグを詰めて消すと、表の別セルの数字が繋がって偽の金額になる
    # （<td>5</td><td>980円</td> → 5980円）。空白で区切る。
    # 価格語と額が別セルにあっても正規表現側が空白を許容するので検出は落ちない。
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip()

    if any(m in title for m in SKIP_MARKS):
        issues.append("内部メモが公開されている")

    if not post.get("featured_media"):
        issues.append("アイキャッチ未設定")

    cats = post.get("categories") or []
    if not cats or cats == [UNCATEGORIZED_ID]:
        issues.append("カテゴリが未分類")

    if len(text) < MIN_CHARS:
        issues.append(f"本文{len(text)}字（下限{MIN_CHARS}字）")

    links = len(re.findall(r"af\.moshimo\.com/af/c/click|px\.a8\.net/svt/ejp", body))
    if links == 0:
        issues.append("アフィリンクが0本")

    if "アフィリエイトリンクが含まれます" not in text and "PR" not in text:
        issues.append("PR表記なし")

    # 料金・制度は改定される。日付が無いと改定後は訂正ではなく虚偽になる。
    # ただし「1円も残らなかった」「0円」のような修辞は料金ではない。
    # サービスの価格として書かれているものだけを見る。
    price = re.search(
        # 「月額1,848円」「受講料は25万円」のように、価格を指す語のあとに来る額
        r"(?:月額|年額|税込|税抜|料金|価格|受講料|授業料|総額|費用|月)"
        r"[はがのも、\s]{0,3}[0-9０-９][0-9０-９,，\.]*\s*万?円"
        # 「5,980円／月」のように単位が後ろに付く形
        r"|[0-9０-９][0-9０-９,，\.]*\s*万?円\s*(?:／|/)\s*(?:月|年|回|人)"
        # 桁区切りのある具体額（171,600円）。修辞では出てこない書き方
        r"|[0-9０-９]{1,3}(?:[,，][0-9０-９]{3})+\s*円",
        text)
    has_date = re.search(r"20[0-9]{2}年\s*[0-9]{1,2}\s*月.{0,6}時点|"
                         r"20[0-9]{2}[-/][0-9]{1,2}[-/][0-9]{1,2}\s*時点", text)
    if price and not has_date:
        issues.append(f"料金（{price.group(0).strip()}）があるのに基準日がない")

    return issues


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    posts = published()
    print(f"公開中 {len(posts)}本を検査\n")

    bad, reasons = [], Counter()
    for p in posts:
        iss = audit(p)
        if iss:
            bad.append((p, iss))
            for i in iss:
                reasons[re.sub(r"（.*?）", "", i)] += 1

    stamp = date.today().isoformat()
    L = [f"# 公開記事の点検 {stamp}\n\n",
         f"公開中 {len(posts)}本 / 要修正 **{len(bad)}本**\n\n"]

    if reasons:
        L.append("## 内訳\n\n| 指摘 | 件数 |\n|---|---|\n")
        for r, n in reasons.most_common():
            L.append(f"| {r} | {n} |\n")

    if bad:
        L.append("\n## 要修正の記事\n\n| ID | 指摘 | タイトル |\n|---|---|---|\n")
        for p, iss in bad:
            t = re.sub(r"<[^>]+>", "", p["title"]["rendered"])[:38]
            L.append(f"| {p['id']} | {' / '.join(iss)} | {t} |\n")
            print(f"[{p['id']}] {' / '.join(iss)}")
            print(f"      {t}")
    else:
        print("問題なし")

    (OUT / "AUDIT.md").write_text("".join(L), encoding="utf-8")
    print(f"\n要修正 {len(bad)}/{len(posts)}本")
    for r, n in reasons.most_common():
        print(f"  {n:>3}件  {r}")


if __name__ == "__main__":
    main()
