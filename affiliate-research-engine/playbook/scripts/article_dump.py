#!/usr/bin/env python3
"""
article_dump.py
指定した記事の本文を、そのままファイルに落とす。

改修案を書くには、見出しだけでなく全文が要る。
実行環境からサイトへ到達できないことがあるので、
Actions 側で取ってリポジトリに置く。

  POSTS=310,304 python article_dump.py
出力: workspace/claims/posts/<id>.html / <id>.txt

**状態だけ見たいとき**は `POSTS=state:310,304` と書く。
アイキャッチを差し替える前に「今どのメディアが付いているか」を控える用。
本文のファイルは書かず、標準出力へ1行ずつ出すだけなのでリポジトリを汚さない。
"""
import os
import re
import sys
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings()
sys.path.insert(0, str(Path(__file__).parent))
import quality_rules as _q
import wp_audit as _wa

OUT = Path("affiliate-research-engine/playbook/workspace/claims/posts")
IDS = [x.strip() for x in os.environ.get("POSTS", "").split(",") if x.strip()]

WP = "https://sakura-eigo.com/wp-json/wp/v2"
AUTH = ("rei.00pt2342@gmail.com", os.environ.get("WP_APP_PASSWORD", ""))
UA = {"User-Agent": "Mozilla/5.0"}


def raw_content(pid):
    """**編集画面に入っている本文そのもの。**

    rendered のほうは目次プラグインが差し込んだHTMLが混ざる。
    文単位で差し替えるときにそれを掴むと、目次が本文へ焼き付いてしまう
    （2026-08-09にその手前で気づいた）。
    """
    r = requests.get(f"{WP}/posts/{pid}", auth=AUTH, headers=UA,
                     params={"context": "edit"}, verify=False, timeout=45)
    return r.json()["content"]["raw"] if r.status_code == 200 else ""


def state_only(ids):
    """今の featured_media と画像URLを出すだけ。**何も書かない。**"""
    print("post_id,status,featured_media,media_url,alt")
    for pid in ids:
        r = requests.get(f"{WP}/posts/{pid}", auth=AUTH, headers=UA,
                         params={"_fields": "id,status,featured_media"},
                         verify=False, timeout=45)
        if r.status_code != 200:
            print(f"{pid},取得できない,,,")
            continue
        p = r.json()
        url = alt = ""
        if p.get("featured_media"):
            m = requests.get(f"{WP}/media/{p['featured_media']}", auth=AUTH,
                             headers=UA, verify=False, timeout=45,
                             params={"_fields": "source_url,alt_text"})
            if m.status_code == 200:
                url = m.json().get("source_url", "")
                alt = (m.json().get("alt_text") or "").replace(",", "、")
        print(f"{pid},{p.get('status')},{p.get('featured_media')},{url},{alt}")


def main():
    if IDS and IDS[0].startswith("state:"):
        state_only([IDS[0].split(":", 1)[1]] + IDS[1:])
        return
    OUT.mkdir(parents=True, exist_ok=True)
    want = set(IDS)
    for p in _wa.published():
        pid = str(p["id"])
        if want and pid not in want:
            continue
        html = p.get("content", {}).get("rendered", "")
        title = re.sub(r"<[^>]+>", "", p["title"]["rendered"])
        (OUT / f"{pid}.html").write_text(html, encoding="utf-8")
        raw = raw_content(pid)
        if raw:
            (OUT / f"{pid}.raw.html").write_text(raw, encoding="utf-8")
        text = "\n".join(
            f"[{m.group(1).lower()}] {_q.strip_tags(m.group(2))}"
            for m in re.finditer(
                r"<(p|li|h2|h3|h4|blockquote)\b[^>]*>(.*?)</\1>",
                html, re.DOTALL | re.I)
            if _q.strip_tags(m.group(2)).strip())
        (OUT / f"{pid}.txt").write_text(
            f"# {title}\n{p.get('link','')}\n\n{text}\n", encoding="utf-8")
        print(f"[{pid}] {title} … {len(html)}字")


if __name__ == "__main__":
    main()
