#!/usr/bin/env python3
"""
draft_dump.py
下書きの本文を取り出す。公開記事のダンプ（article_dump.py）は
status=publish しか見ないので、下書きはこちらで取る。

  POSTS=647 python draft_dump.py
出力: workspace/claims/drafts/<id>.raw.html / <id>.json
"""
import json
import os
import sys
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings()
WP = "https://sakura-eigo.com/wp-json/wp/v2"
AUTH = ("rei.00pt2342@gmail.com", os.environ.get("WP_APP_PASSWORD", ""))
UA = {"User-Agent": "Mozilla/5.0"}
OUT = Path("affiliate-research-engine/playbook/workspace/claims/drafts")
POSTS = [x.strip() for x in os.environ.get("POSTS", "").split(",") if x.strip()]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ids = POSTS
    if not ids:
        r = requests.get(f"{WP}/posts", auth=AUTH, headers=UA, verify=False,
                         timeout=45,
                         params={"status": "draft,future,pending",
                                 "per_page": 100, "context": "edit"})
        ids = [str(p["id"]) for p in r.json()] if r.status_code == 200 else []
        print(f"下書き・予約 {len(ids)}本: {' '.join(ids)}")
    for pid in ids:
        g = requests.get(f"{WP}/posts/{pid}", auth=AUTH, headers=UA,
                         params={"context": "edit"}, verify=False, timeout=45)
        if g.status_code != 200:
            print(f"[{pid}] 取得できず {g.status_code}")
            continue
        p = g.json()
        (OUT / f"{pid}.raw.html").write_text(p["content"]["raw"],
                                             encoding="utf-8")
        (OUT / f"{pid}.json").write_text(json.dumps({
            "id": p["id"], "status": p["status"],
            "title": p["title"]["raw"], "slug": p["slug"],
            "excerpt": p["excerpt"]["raw"], "categories": p["categories"],
            "tags": p.get("tags", []), "featured_media": p["featured_media"],
            "date": p.get("date"), "link": p.get("link"),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[{pid}] {p['status']} / {p['title']['raw'][:40]} / "
              f"{len(p['content']['raw'])}字")
    print(f"\n→ {OUT}")


if __name__ == "__main__":
    main()
