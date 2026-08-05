#!/usr/bin/env python3
"""
wp_recent.py
直近の投稿を一覧する。記事IDを調べるためだけの小さな道具。

Threads作り直しやX告知は記事IDを引数に取るので、
毎回WordPressを開いてIDを探さなくて済むようにする。
"""
import os
import re
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings()

WP_BASE = "https://sakura-eigo.com/wp-json/wp/v2"
WP_USER = "rei.00pt2342@gmail.com"
WP_PASS = os.environ.get("WP_APP_PASSWORD", "")
LIMIT = int(os.environ.get("LIMIT", "15"))
OUT = Path("affiliate-research-engine/playbook/workspace/site")


def main():
    r = requests.get(
        f"{WP_BASE}/posts",
        auth=(WP_USER, WP_PASS),
        params={"per_page": LIMIT, "orderby": "date", "order": "desc",
                "status": "publish,draft,pending,future,private",
                "_fields": "id,date,status,title,link,featured_media,categories"},
        headers={"User-Agent": "Mozilla/5.0"}, verify=False, timeout=40)
    if r.status_code != 200:
        print(f"取得失敗 HTTP {r.status_code}")
        raise SystemExit(1)

    posts = r.json()
    lines = [f"# 直近の投稿 {LIMIT}件\n\n",
             "| ID | 日付 | 状態 | アイキャッチ | タイトル |\n|---|---|---|---|---|\n"]
    print(f"{'ID':>5}  {'日付':<10} {'状態':<8} {'画像':<4} タイトル")
    print("-" * 76)
    for p in posts:
        title = re.sub(r"<[^>]+>", "", p["title"]["rendered"])
        eye = "あり" if p.get("featured_media") else "なし"
        date = p["date"][:10]
        print(f"{p['id']:>5}  {date:<10} {p['status']:<8} {eye:<4} {title[:38]}")
        lines.append(f"| {p['id']} | {date} | {p['status']} | {eye} | {title[:44]} |\n")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "RECENT.md").write_text("".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
