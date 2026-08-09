#!/usr/bin/env python3
"""
eyecatch_survey.py
公開済みのアイキャッチを回収して、**テイスト別のコンタクトシート**を作る。

いま手元にあるもの:
  workspace/seo/eyecatch/<記事ID>.jpg … 文字カードへ差し替える**前**の実物（49枚）
  workspace/seo/eyecatch_new/*.png     … 文字カード型（27枚）
  backups/<日>/eyecatch/<記事ID>.json  … 差し替え前の media ID（20件）

足りないのは**アップロード日**。メディアAPIから取って、
2026-08-07（固定ちびキャラのテンプレートが入った日）で前後に分ける。

  python eyecatch_survey.py
出力:
  workspace/seo/survey/CONTACT_<群>.jpg   … サムネイル一覧
  workspace/seo/survey/INVENTORY.csv      … 記事ID・メディアID・URL・日付・群
"""
import csv
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import urllib3
from PIL import Image, ImageDraw, ImageFont

urllib3.disable_warnings()
sys.path.insert(0, str(Path(__file__).parent))
import wp_audit as _wa

JST = timezone(timedelta(hours=9))
WP = "https://sakura-eigo.com/wp-json/wp/v2"
AUTH = ("rei.00pt2342@gmail.com", os.environ.get("WP_APP_PASSWORD", ""))
UA = {"User-Agent": "Mozilla/5.0"}
WS = Path("affiliate-research-engine/playbook/workspace")
OLD_DIR = WS / "seo/eyecatch"
CARD_DIR = WS / "seo/eyecatch_new"
OUT = WS / "seo/survey"
BK = WS / "backups"

# 固定ちびキャラのテンプレートが入った日
PIVOT = "2026-08-07"

FONTS = ["/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
         "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf"]


def font(size):
    for p in FONTS:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def media(mid):
    if not mid:
        return {}
    r = requests.get(f"{WP}/media/{mid}", auth=AUTH, headers=UA, verify=False,
                     timeout=40)
    return r.json() if r.status_code == 200 else {}


def sheet(items, title, path, cols=5):
    """サムネイルを並べて1枚にする。1枚ずつに記事IDと群を書く。"""
    if not items:
        return None
    tw, th, pad, lab = 320, 180, 14, 34
    rows = (len(items) + cols - 1) // cols
    W = cols * (tw + pad) + pad
    H = 64 + rows * (th + lab + pad) + pad
    im = Image.new("RGB", (W, H), (250, 248, 249))
    d = ImageDraw.Draw(im)
    d.text((pad, 20), title, font=font(28), fill=(60, 50, 55))
    for i, (pid, p, note) in enumerate(items):
        x = pad + (i % cols) * (tw + pad)
        y = 64 + (i // cols) * (th + lab + pad)
        try:
            t = Image.open(p).convert("RGB")
            t.thumbnail((tw, th))
            im.paste(t, (x + (tw - t.width) // 2, y + (th - t.height) // 2))
        except Exception:
            d.rectangle([x, y, x + tw, y + th], outline=(200, 190, 195))
        d.rectangle([x, y, x + tw, y + th], outline=(214, 204, 209))
        d.text((x + 2, y + th + 6), f"{pid}  {note}"[:34], font=font(20),
               fill=(90, 78, 84))
    im.save(path, "JPEG", quality=88)
    return path


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    posts = {str(p["id"]): p for p in _wa.published()}

    # 差し替え前の media ID
    oldmid = {}
    for f in sorted(BK.glob("*/eyecatch/*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        oldmid[str(d["id"])] = d.get("old_featured_media")

    rows = []
    for pid, p in sorted(posts.items(), key=lambda x: int(x[0])):
        # 「元の画像」= 差し替え前があればそれ、無ければ現在のもの
        mid = oldmid.get(pid) or p.get("featured_media")
        m = media(mid)
        date = (m.get("date") or "")[:10]
        url = m.get("source_url", "")
        local = OLD_DIR / f"{pid}.jpg"
        group = ("旧テイスト" if date and date < PIVOT
                 else "新テイスト" if date else "不明")
        rows.append({"post_id": pid, "media_id": mid or "",
                     "uploaded": date, "url": url, "group": group,
                     "replaced": "yes" if pid in oldmid else "no",
                     "local": str(local) if local.exists() else "",
                     "title": re.sub(r"<[^>]+>", "",
                                     p["title"]["rendered"])[:40]})
        print(f"[{pid}] {date} {group} media {mid}")

    # 文字カード型（今回こちらで作ったもの）
    for f in sorted(CARD_DIR.glob("*.png")):
        rows.append({"post_id": f.stem, "media_id": "", "uploaded": "2026-08-09",
                     "url": "", "group": "文字カード型", "replaced": "-",
                     "local": str(f), "title": "（差し替えで作った文字カード）"})

    with open(OUT / "INVENTORY.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    for g, fn in (("旧テイスト", "CONTACT_old.jpg"),
                  ("新テイスト", "CONTACT_new.jpg"),
                  ("文字カード型", "CONTACT_card.jpg"),
                  ("不明", "CONTACT_unknown.jpg")):
        items = [(r["post_id"], r["local"], r["uploaded"])
                 for r in rows if r["group"] == g and r["local"]]
        if items:
            sheet(items, f"{g}（{len(items)}枚） {stamp}", OUT / fn)
            print(f"{g}: {len(items)}枚 → {fn}")

    from collections import Counter
    c = Counter(r["group"] for r in rows)
    L = [f"# アイキャッチの棚卸し {stamp}\n\n",
         f"分ける基準日: **{PIVOT}**（固定ちびキャラのテンプレートが入った日）\n\n",
         "| 群 | 枚数 |\n|---|---|\n"]
    for k, v in c.most_common():
        L.append(f"| {k} | {v} |\n")
    L.append("\n| 記事 | メディアID | アップロード | 群 | 差し替え済み | タイトル |\n"
             "|---|---|---|---|---|---|\n")
    for r in rows:
        L.append(f"| {r['post_id']} | {r['media_id']} | {r['uploaded']} | "
                 f"{r['group']} | {r['replaced']} | {r['title']} |\n")
    (OUT / "INVENTORY.md").write_text("".join(L), encoding="utf-8")
    print(f"\n{dict(c)} → {OUT}")


if __name__ == "__main__":
    main()
