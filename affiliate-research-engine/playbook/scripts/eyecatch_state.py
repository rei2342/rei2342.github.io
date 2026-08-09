#!/usr/bin/env python3
"""
eyecatch_state.py
指定した記事の**今の状態**を持ち帰るだけ。何も書き換えない。

差し替えの前に「今どのメディアが付いているか」を控えておかないと、
戻せなくなる。開発環境から sakura-eigo.com へは出られないので、
GitHub Actions から実行して結果をリポジトリへ置く。

  POSTS="304,282,..." python eyecatch_state.py
出力: workspace/seo/eyecatch/STATE_<ラベル>.yaml
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import urllib3
import yaml

urllib3.disable_warnings()

JST = timezone(timedelta(hours=9))
WP_BASE = "https://sakura-eigo.com/wp-json/wp/v2"
WP_USER = "rei.00pt2342@gmail.com"
WP_PASS = os.environ.get("WP_APP_PASSWORD", "")
AUTH = (WP_USER, WP_PASS)
UA = {"User-Agent": "Mozilla/5.0"}
LABEL = os.environ.get("LABEL", "next20")
OUT = Path("affiliate-research-engine/playbook/workspace/seo/eyecatch")


def get(path, **params):
    r = requests.get(f"{WP_BASE}/{path}", auth=AUTH, params=params,
                     headers=UA, verify=False, timeout=40)
    return r.json() if r.status_code == 200 else None


def main():
    ids = [x.strip() for x in os.environ.get("POSTS", "").split(",")
           if x.strip()]
    if not ids:
        print("POSTS が空。")
        sys.exit(1)

    rows = []
    for pid in ids:
        p = get(f"posts/{pid}",
                _fields="id,title,slug,status,date,link,featured_media")
        if not p:
            rows.append({"post_id": int(pid), "error": "取得できない"})
            print(f"[{pid}] 取得できない")
            continue
        m = None
        if p.get("featured_media"):
            m = get(f"media/{p['featured_media']}",
                    _fields="id,source_url,alt_text,date")
        rows.append({
            "post_id": p["id"],
            "title": p["title"]["rendered"],
            "slug": p["slug"],
            "status": p["status"],
            "link": p["link"],
            "featured_media": p.get("featured_media"),
            "media_url": (m or {}).get("source_url"),
            "media_alt": (m or {}).get("alt_text"),
            "media_uploaded": (m or {}).get("date"),
        })
        print(f"[{pid}] fm={p.get('featured_media')} "
              f"{(m or {}).get('source_url', '')}")

    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / f"STATE_{LABEL}.yaml"
    f.write_text(yaml.safe_dump({
        "label": LABEL,
        "checked_at": datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST"),
        "note": "取得のみ。**何も書き換えていない。**",
        "count": len(rows),
        "posts": rows,
    }, allow_unicode=True, sort_keys=False, width=200), encoding="utf-8")
    print(f"\n→ {f}")


if __name__ == "__main__":
    main()
