#!/usr/bin/env python3
"""
eyecatch_mockup.py
確認用の見本を作る。**WordPressへは何も送らない。**

作るもの:
  1. REFERENCE_COMPARE.jpg … 参照候補3枚の全体と顔の拡大、優先順位つき
  2. OVERLAY_DEMO.jpg      … ブログ用の文字合成の見本（合成の仕組みの確認）
  3. NOTE_CROP_DEMO.jpg    … note用 1.91:1 クロップの見本
  4. AI6_CONTACT.jpg       … AI6本を並べたコンタクトシート

**2〜4はイラストのマスターがまだ無いので、A判定の既存画像を
「マスターの代わり」として使っている。** 完成版ではない。
文字の位置・大きさ・可読性・クロップの安全域を見るためのもの。

  python eyecatch_mockup.py
出力: workspace/seo/survey/*.jpg
"""
import os
import sys
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
import eyecatch_spec as es

SRC = ROOT / "workspace/seo/eyecatch"
OUT = ROOT / "workspace/seo/survey"

FONTS_B = ["/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
           "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf"]
FONTS_R = ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
           "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf"]


def font(size, bold=True):
    for p in (FONTS_B if bold else FONTS_R):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# ── 1. 参照候補の比較 ────────────────────────────────
# 顔の位置は3枚を目で見て決めた（1200x675 での座標）
FACE_BOX = {"521": (620, 0, 900, 250),
            "273": (660, 40, 940, 330),
            "297": (590, 40, 890, 320)}


def reference_compare(spec):
    order = spec["reference_assets"]["priority_order"]
    W, cell_h, pad = 1680, 300, 20
    H = 96 + len(order) * (cell_h + pad) + pad
    im = Image.new("RGB", (W, H), (250, 248, 249))
    d = ImageDraw.Draw(im)
    d.text((pad, 24), "参照候補の比較（優先順位つき・確定前）",
           font=font(34), fill=(60, 50, 55))
    d.text((pad, 66), "上から順に優先する。食い違ったら上を採る。",
           font=font(22, False), fill=(120, 105, 112))

    for i, ref in enumerate(order):
        pid = str(ref["source_post"])
        y = 96 + i * (cell_h + pad)
        src = Image.open(SRC / f"{pid}.jpg").convert("RGB")

        full = src.copy()
        full.thumbnail((470, cell_h - 40))
        im.paste(full, (pad, y + 20))

        box = FACE_BOX.get(pid)
        if box:
            face = src.crop(box).resize((240, 240), Image.LANCZOS)
            im.paste(face, (pad + 490, y + 20))
            d.rectangle([pad + 490, y + 20, pad + 730, y + 260],
                        outline=(214, 204, 209), width=2)

        tx = pad + 760
        d.text((tx, y + 18), f"{i + 1}. {ref['slot']}", font=font(28),
               fill=(200, 110, 140))
        d.text((tx, y + 58), f"記事{pid} / メディア{ref['source_media_id']}",
               font=font(22, False), fill=(120, 105, 112))
        lines = [("採るもの", ref["take"]),
                 ("採らないもの", ref["do_not_take"]),
                 ("理由", ref["why"])]
        yy = y + 96
        for label, body in lines:
            d.text((tx, yy), label, font=font(20), fill=(150, 116, 124))
            yy += 26
            for chunk in [body[j:j + 34] for j in range(0, len(body), 34)]:
                d.text((tx + 12, yy), chunk, font=font(21, False),
                       fill=(74, 58, 63))
                yy += 27
            yy += 4
        d.line([(pad, y + cell_h + 8), (W - pad, y + cell_h + 8)],
               fill=(228, 220, 224))
    im.save(OUT / "REFERENCE_COMPARE.jpg", "JPEG", quality=90)
    return OUT / "REFERENCE_COMPARE.jpg"


# ── 2. ブログ用の文字合成 ────────────────────────────
def compose_blog(spec, master, lead, sub, accent_hex, scrim=True):
    """仕様の text_overlay どおりに合成する。値は全部 YAML から。"""
    t = spec["text_overlay"]
    W, H = spec["blog_export"]["size"]
    im = master.convert("RGB").resize((W, H), Image.LANCZOS)

    if scrim:
        # 左半分だけ、白のグラデーションを薄く敷く
        g = Image.new("L", (W, H), 0)
        gd = ImageDraw.Draw(g)
        for x in range(700):
            gd.line([(x, 0), (x, H)], fill=int(140 * (1 - x / 700)))
        im = Image.composite(Image.new("RGB", (W, H), (255, 255, 255)), im, g)

    d = ImageDraw.Draw(im)
    lx, ly = t["lead"]["origin"]
    f_lead = font(t["lead"]["size_px"], True)
    f_sub = font(t["sub"]["size_px"], False)
    y = ly
    for line in lead.split("\n")[:t["lead"]["max_lines"]]:
        d.text((lx, y), line, font=f_lead, fill=hexrgb(t["lead"]["color"]))
        y += t["lead"]["size_px"] + t["lead"]["line_gap_px"]
    bar_y = y + 6
    d.rounded_rectangle([lx, bar_y, lx + 120, bar_y + 6], radius=3,
                        fill=hexrgb(accent_hex))
    d.text((lx, bar_y + t["sub"]["offset_below_lead_px"]), sub, font=f_sub,
           fill=hexrgb(t["sub"]["color"]))
    return im


# ── 3. note用クロップ ────────────────────────────────
def crop_note(spec, master):
    """1.91:1 へ。**右寄せ**で切るので、左を落としても主題が残る。"""
    W, H = spec["note_export"]["size"]
    src = master.convert("RGB")
    target = W / H
    sw, sh = src.size
    if sw / sh > target:
        nw = int(sh * target)
        left = sw - nw          # 右端に寄せる
        src = src.crop((left, 0, sw, sh))
    else:
        nh = int(sw / target)
        top = (sh - nh) // 2
        src = src.crop((0, top, sw, top + nh))
    return src.resize((W, H), Image.LANCZOS)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    spec = es.load_spec()
    doc = es.load_articles(ROOT / "config/eyecatch/articles-ai-cluster.yaml")
    cat = doc["category"]
    accent = spec["category_colors"][cat]["hex"]

    p = reference_compare(spec)
    print(f"→ {p.name}")

    # マスターの代わりに使うA判定の画像。記事の内容とは無関係
    STAND_IN = {993: "283", 995: "315", 997: "521",
                999: "286", 1001: "305", 1003: "297"}

    # 合成の見本（1枚だけ大きく）
    a0 = doc["articles"][0]
    m0 = Image.open(SRC / f"{STAND_IN[a0['post_id']]}.jpg")
    blog0 = compose_blog(spec, m0, a0["lead_text"], a0["sub_text"], accent)
    demo = Image.new("RGB", (1240, 1180), (250, 248, 249))
    dd = ImageDraw.Draw(demo)
    dd.text((20, 18), "ブログ用の文字合成の見本（1200×675）",
            font=font(30), fill=(60, 50, 55))
    dd.text((20, 56),
            "背景は仮のマスター（A判定の既存画像）。完成版ではない。"
            "見るのは文字の位置・大きさ・読みやすさ。",
            font=font(20, False), fill=(120, 105, 112))
    demo.paste(blog0, (20, 92))
    dd.rectangle([20, 92, 20 + 600, 92 + 675], outline=(210, 120, 150), width=2)
    dd.text((28, 92 + 680), "赤い枠が文字セーフエリア（左半分）",
            font=font(20, False), fill=(200, 110, 140))
    small = blog0.copy()
    small.thumbnail((320, 180))
    demo.paste(small, (20, 92 + 715))
    dd.text((360, 92 + 715), "サムネイル（320px）でも読めるか",
            font=font(22), fill=(60, 50, 55))
    dd.text((360, 92 + 748),
            "1行14字・リード62px・補助30pxの設定で確認",
            font=font(20, False), fill=(120, 105, 112))
    nocrim = compose_blog(spec, m0, a0["lead_text"], a0["sub_text"], accent,
                          scrim=False)
    nc = nocrim.copy()
    nc.thumbnail((320, 180))
    demo.paste(nc, (700, 92 + 715))
    dd.text((700, 92 + 900), "白のグラデーション無しの場合",
            font=font(20, False), fill=(120, 105, 112))
    demo.save(OUT / "OVERLAY_DEMO.jpg", "JPEG", quality=90)
    print("→ OVERLAY_DEMO.jpg")

    # note用クロップの見本
    nd = Image.new("RGB", (1280, 760), (250, 248, 249))
    ndd = ImageDraw.Draw(nd)
    ndd.text((20, 18), "note用クロップの見本（1.91:1・文字なし）",
             font=font(30), fill=(60, 50, 55))
    ndd.text((20, 56),
             "右寄せで切る。左半分はブログの文字用なので、切っても主題が残る。",
             font=font(20, False), fill=(120, 105, 112))
    src16 = m0.convert("RGB").resize((1200, 675), Image.LANCZOS)
    s1 = src16.copy(); s1.thumbnail((580, 340))
    nd.paste(s1, (20, 100))
    ndd.text((20, 100 + s1.height + 8), "16:9 マスター（文字なし）",
             font=font(22), fill=(60, 50, 55))
    n1 = crop_note(spec, m0); n1.thumbnail((580, 340))
    nd.paste(n1, (640, 100))
    ndd.text((640, 100 + n1.height + 8), "1.91:1 へ右寄せクロップ",
             font=font(22), fill=(60, 50, 55))
    ndd.text((20, 480),
             "ブログ版（文字あり）とnote版（文字なし）を並べたところ",
             font=font(22), fill=(60, 50, 55))
    b2 = blog0.copy(); b2.thumbnail((580, 330))
    nd.paste(b2, (20, 512))
    n2 = crop_note(spec, m0); n2.thumbnail((580, 330))
    nd.paste(n2, (640, 512))
    nd.save(OUT / "NOTE_CROP_DEMO.jpg", "JPEG", quality=90)
    print("→ NOTE_CROP_DEMO.jpg")

    # AI6本のコンタクトシート（ブログ版とnote版を上下に）
    cols, tw, th, pad = 3, 380, 214, 16
    rows = 2
    W = cols * (tw + pad) + pad
    H = 110 + rows * (th * 2 + 76 + pad) + pad
    cs = Image.new("RGB", (W, H), (250, 248, 249))
    cd = ImageDraw.Draw(cs)
    cd.text((pad, 20), "AI英語学習6本（上=ブログ版・下=note版）",
            font=font(32), fill=(60, 50, 55))
    cd.text((pad, 60),
            "背景はすべて仮のマスター。**完成版ではない。**"
            "見るのは文言・人物の有無・シリーズとしての揃い方。",
            font=font(20, False), fill=(120, 105, 112))
    for i, a in enumerate(doc["articles"]):
        x = pad + (i % cols) * (tw + pad)
        y = 110 + (i // cols) * (th * 2 + 76 + pad)
        m = Image.open(SRC / f"{STAND_IN[a['post_id']]}.jpg")
        b = compose_blog(spec, m, a["lead_text"], a["sub_text"], accent)
        b.thumbnail((tw, th)); cs.paste(b, (x, y))
        n = crop_note(spec, m)
        n.thumbnail((tw, th)); cs.paste(n, (x, y + th + 6))
        person = "人物あり" if a["with_person"] else "人物なし"
        cd.text((x, y + th * 2 + 14), f"{a['post_id']}  {person}",
                font=font(21), fill=(60, 50, 55))
        cd.text((x, y + th * 2 + 40),
                a["lead_text"].replace("\n", " / ")[:26],
                font=font(19, False), fill=(120, 105, 112))
    cs.save(OUT / "AI6_CONTACT.jpg", "JPEG", quality=88)
    print("→ AI6_CONTACT.jpg")


if __name__ == "__main__":
    main()
