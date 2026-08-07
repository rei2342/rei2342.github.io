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
sys.path.insert(0, str(Path(__file__).parent))
import quality_rules as _q

WP_BASE = "https://sakura-eigo.com/wp-json/wp/v2"
WP_USER = "rei.00pt2342@gmail.com"
WP_PASS = os.environ.get("WP_APP_PASSWORD", "")
MIN_CHARS = int(os.environ.get("MIN_CHARS", "3000"))
OUT = Path("affiliate-research-engine/playbook/workspace/site")

UNCATEGORIZED_ID = 1
SKIP_MARKS = ("【Threads用】", "【メモ】", "【社内")


def media_urls():
    """メディアID → URL の対応を取る。

    アイキャッチのファイル名が日本語だと、MetaのクローラーがURLを
    取りに行けず、Threads/Facebookのプレビュー画像が出ない
    （2026-08-07に「ChatGPT-Image-2026年8月7日-11_04_03.png」で発生）。
    ファイル自体は200で返るので、外形からは気づけない。
    """
    urls, page = {}, 1
    while True:
        r = requests.get(f"{WP_BASE}/media", auth=(WP_USER, WP_PASS),
                         params={"per_page": 100, "page": page,
                                 "_fields": "id,source_url"},
                         headers={"User-Agent": "Mozilla/5.0"},
                         verify=False, timeout=40)
        if r.status_code != 200:
            break
        b = r.json()
        if not b:
            break
        urls.update({m["id"]: m.get("source_url", "") for m in b})
        if len(b) < 100:
            break
        page += 1
    return urls


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
    text = _q.strip_tags(body)

    if any(m in title for m in SKIP_MARKS):
        issues.append("内部メモが公開されている")

    fm = post.get("featured_media")
    if not fm:
        issues.append("アイキャッチ未設定")
    else:
        url = (MEDIA or {}).get(fm, "")
        # 半角英数以外がURLに入っていると、SNSのプレビュー画像が出ない
        if url and not url.isascii():
            issues.append(f"アイキャッチのファイル名に日本語が入っている（{url.split('/')[-1][:40]}）")

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

    # 料金・制度・断定・導線の誠実さは quality_rules に集約している。
    # 生成時（article_rewriter.audit）と同じ基準で見るため。
    price = _q.price_without_basedate(text)
    if price:
        issues.append(f"料金（{price}）があるのに基準日がない")

    hype = _q.hype_words(text)
    if hype:
        issues.append(f"根拠を超える断定: {'・'.join(hype)}")

    if _q.institutional_without_source(text):
        issues.append("制度・年齢条件の話があるのに確認日も出典もない")

    if _q.missing_caveat(body, text):
        issues.append("案件を紹介しているのに、合わない人も注意点も書いていない")

    return issues


MEDIA = {}


def main():
    global MEDIA
    OUT.mkdir(parents=True, exist_ok=True)
    MEDIA = media_urls()
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
