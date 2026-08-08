#!/usr/bin/env python3
"""
article_dump.py
指定した記事の本文を、そのままファイルに落とす。

改修案を書くには、見出しだけでなく全文が要る。
実行環境からサイトへ到達できないことがあるので、
Actions 側で取ってリポジトリに置く。

  POSTS=310,304 python article_dump.py
出力: workspace/claims/posts/<id>.html / <id>.txt
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


def main():
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
