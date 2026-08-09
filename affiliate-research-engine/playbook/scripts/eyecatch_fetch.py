#!/usr/bin/env python3
"""
eyecatch_fetch.py
アイキャッチ画像を取得して、**リポジトリに置く**。

tesseract は装飾された文字や手書き風のロゴを読めない。
「機械で読めない」で止めないために、画像そのものを持ち帰って
目で確認できるようにする。そのままだと重いので長辺1200pxへ縮める。

  POSTS=546,27,32 python eyecatch_fetch.py
出力: workspace/seo/eyecatch/<id>.jpg / EYECATCH_FILES.md
"""
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

import requests
import urllib3
from PIL import Image

urllib3.disable_warnings()
sys.path.insert(0, str(Path(__file__).parent))
import wp_audit as _wa

OUT = Path("affiliate-research-engine/playbook/workspace/seo/eyecatch")
JST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0"}
POSTS = [x.strip() for x in os.environ.get("POSTS", "").split(",") if x.strip()]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    posts = {str(p["id"]): p for p in _wa.published()}
    want = POSTS or sorted(posts, key=int)

    L = [f"# アイキャッチ画像の実物 {stamp}\n\n",
         "tesseract で読めなかった画像を目で見るために、実物を置いた。\n"
         "長辺1200pxへ縮めてある。\n\n",
         "| 記事 | 元の画像 | 置いた場所 | サイズ |\n|---|---|---|---|\n"]
    for pid in want:
        p = posts.get(pid)
        if not p:
            L.append(f"| {pid} | — | — | 公開記事に無い |\n")
            continue
        mid = p.get("featured_media")
        src = ""
        if mid:
            m = requests.get(
                f"https://sakura-eigo.com/wp-json/wp/v2/media/{mid}",
                headers=UA, verify=False, timeout=40)
            if m.status_code == 200:
                src = m.json().get("source_url", "")
        if not src:
            L.append(f"| {pid} | — | — | アイキャッチ無し |\n")
            continue
        r = requests.get(src, headers=UA, verify=False, timeout=60)
        if r.status_code != 200:
            L.append(f"| {pid} | {src.rsplit('/', 1)[-1]} | — | "
                     f"HTTP {r.status_code} |\n")
            continue
        im = Image.open(BytesIO(r.content)).convert("RGB")
        w, h = im.size
        if max(w, h) > 1200:
            s = 1200 / max(w, h)
            im = im.resize((int(w * s), int(h * s)), Image.LANCZOS)
        dst = OUT / f"{pid}.jpg"
        im.save(dst, "JPEG", quality=88)
        L.append(f"| {pid} | {src.rsplit('/', 1)[-1]} | "
                 f"`workspace/seo/eyecatch/{pid}.jpg` | "
                 f"{w}x{h} → {im.size[0]}x{im.size[1]} |\n")
        print(f"[{pid}] {w}x{h} → {dst} {dst.stat().st_size // 1024}KB")

    (OUT.parent / "EYECATCH_FILES.md").write_text("".join(L), encoding="utf-8")
    print(f"\n→ {OUT}")


if __name__ == "__main__":
    main()
