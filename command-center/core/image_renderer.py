"""IG カルーセル画像（1080x1350）を Pillow で描く。"""
from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "C:/Windows/Fonts/meiryo.ttc",
]
W, H, PAD = 1080, 1350, 96


def _font(size: int) -> ImageFont.FreeTypeFont:
    for f in FONT_CANDIDATES:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def _palette(seed: str) -> tuple[tuple, tuple, tuple]:
    h = int(hashlib.md5(seed.encode()).hexdigest()[:6], 16)
    hue = h % 360
    import colorsys

    bg = tuple(int(c * 255) for c in colorsys.hls_to_rgb(hue / 360, 0.95, 0.35))
    accent = tuple(int(c * 255) for c in colorsys.hls_to_rgb(hue / 360, 0.40, 0.55))
    return bg, accent, (34, 34, 34)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> list[str]:
    lines = []
    for para in (text or "").split("\n"):
        cur = ""
        for ch in para:
            if draw.textlength(cur + ch, font=font) > width:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        lines.append(cur)
    return lines


def render_carousel(slides: list[dict], out_dir: Path, seed: str, handle: str | None = None) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    bg, accent, ink = _palette(seed)
    paths = []
    for i, s in enumerate(slides, 1):
        img = Image.new("RGB", (W, H), bg)
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, 18], fill=accent)
        hf = _font(72 if i == 1 else 58)
        bf = _font(40)
        y = 200 if i == 1 else 150
        for line in _wrap(d, s.get("headline", ""), hf, W - PAD * 2):
            d.text((PAD, y), line, font=hf, fill=accent if i == 1 else ink)
            y += int(hf.size * 1.35)
        y += 50
        for line in _wrap(d, s.get("body", ""), bf, W - PAD * 2):
            if y > H - 200:
                break
            d.text((PAD, y), line, font=bf, fill=ink)
            y += int(bf.size * 1.6)
        foot = _font(30)
        d.text((PAD, H - 110), f"{i}/{len(slides)}", font=foot, fill=accent)
        if handle:
            d.text((W - PAD - d.textlength("@" + handle, font=foot), H - 110), "@" + handle, font=foot, fill=ink)
        p = out_dir / f"slide_{i:02d}.png"
        img.save(p, optimize=True)
        paths.append(str(p))
    return paths
