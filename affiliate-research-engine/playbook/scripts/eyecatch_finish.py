#!/usr/bin/env python3
"""
eyecatch_finish.py
文字なしマスターがそろってから走らせる。**WordPressへは送らない。**

  masters/<記事ID>.png（1920×1080・文字なし）
    → ブログ用 1200×675（固定フォントで文字合成）
    → note用  1200×628（右寄せクロップ・文字なし）
    → 13項目の検査
    → 3種類を並べたコンタクトシート

マスターが1枚でも足りなければ**何もせずに止まる**。
仮画像を作って先へ進めない。

  python eyecatch_finish.py --batch next20
出力: eyecatch-generation-batch/ai-6/out/ と CHECKS.md
"""
import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
import eyecatch_spec as es
import eyecatch_mockup as mk

JST = timezone(timedelta(hours=9))
BATCHES = {
    "ai6": ("ai-6", "config/eyecatch/articles-ai-cluster.yaml"),
    "next20": ("next-20", "config/eyecatch/articles-next20.yaml"),
}
BATCH = OUT = None      # --batch で決まる


def font(size, bold=True):
    return mk.font(size, bold)


def checks(spec, art, master, blog, note):
    """13項目のうち、機械で見られるものを見る。
    人が見る項目（読める・既存と見分けがつく）は理由つきで manual にする。"""
    w, h = spec["master_size"]
    r = []

    r.append(("generated", master.exists(), "マスターが置かれている"))
    ok_size = False
    if master.exists():
        im = Image.open(master)
        ok_size = abs(im.width / im.height - w / h) < 0.01
    r.append(("aspect", ok_size, f"マスターが {spec['master_aspect_ratio']}"))

    # 文字が写り込んでいないかは機械では判定しきれない。
    # **黙って通さず manual にする**
    r.append(("no_text_in_master", None,
              "マスターに文字が無いか。目で見る"))

    r.append(("blog_size", blog.exists()
              and Image.open(blog).size == tuple(spec["blog_export"]["size"]),
              "ブログ用が 1200×675"))
    r.append(("note_size", note.exists()
              and Image.open(note).size == tuple(spec["note_export"]["size"]),
              "note用が 1.91:1"))
    r.append(("note_no_text", spec["note_export"]["text_overlay"] is False,
              "note用に文字を載せていない"))
    r.append(("weight", blog.exists()
              and blog.stat().st_size <= spec["blog_export"]["max_bytes"],
              f"ブログ用が {spec['blog_export']['max_bytes'] // 1024}KB 以下"))
    r.append(("filename", art["filename"].replace("-", "").replace(".jpg", "")
              .isalnum(), "ファイル名が半角英数とハイフン"))
    r.append(("text_matches_body", None,
              "合成した文字が本文と一致するか。目で見る"))
    r.append(("no_unverified_claim",
              not any(ch.isdigit() for ch in
                      art["lead_text"] + art["sub_text"]),
              "画像内文言に数字が無い"))
    r.append(("thumbnail_readable", None,
              "サムネイルで読めるか。コンタクトシートで見る"))
    r.append(("distinct", None, "既存と見分けがつくか。コンタクトシートで見る"))
    r.append(("not_text_card", None,
              "文字カード型になっていないか。目で見る"))
    r.append(("person_policy", None,
              f"人物 {'あり' if art['with_person'] else 'なし'} が"
              f"承認どおりか。目で見る"))
    r.append(("face_matches_521", None if art["with_person"] else True,
              "顔が521から離れていないか。離れていたら不合格"))
    r.append(("no_fake_usage", None,
              "未使用サービスを操作しているように見えないか。目で見る"))
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", default="next20", choices=sorted(BATCHES))
    args = ap.parse_args()
    d, articles = BATCHES[args.batch]
    global BATCH, OUT
    BATCH = ROOT / "eyecatch-generation-batch" / d
    OUT = BATCH / "out"

    spec = es.load_spec()
    doc = es.load_articles(ROOT / articles)
    cat = doc["category"]
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")

    missing = [str(a["post_id"]) for a in doc["articles"]
               if not (BATCH / "masters" / f"{a['post_id']}.png").exists()]
    if missing:
        print("マスターが足りない: " + " ".join(missing))
        print(f"{BATCH}/masters/ へ <記事ID>.png を置いてから、もう一度。")
        print("**仮画像は作らない。** ここで止める。")
        sys.exit(1)

    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for a in doc["articles"]:
        pid = str(a["post_id"])
        m = BATCH / "masters" / f"{pid}.png"
        im = Image.open(m)
        blog = OUT / a["filename"]
        note = OUT / a["filename"].replace(".jpg", "-note.jpg")
        accent = spec["category_colors"].get(
            a.get("category", cat), spec["category_colors"]["_default"])["hex"]
        mk.compose_blog(spec, im, a["lead_text"], a["sub_text"], accent,
                        scrim=False).save(
            blog, "JPEG", quality=spec["blog_export"]["quality"])
        mk.crop_note(spec, im).save(
            note, "JPEG", quality=spec["note_export"]["quality"])
        rows.append((a, m, blog, note, checks(spec, a, m, blog, note)))
        print(f"[{pid}] blog {blog.stat().st_size // 1024}KB / note OK")

    # 3種類を並べたコンタクトシート
    tw, th, pad = 380, 214, 16
    W = 3 * (tw + pad) + pad
    H = 120 + ((len(rows) + 2) // 3) * (th * 3 + 96 + pad) + pad
    cs = Image.new("RGB", (W, H), (250, 248, 249))
    d = ImageDraw.Draw(cs)
    d.text((pad, 20), f"{len(rows)}本 {stamp}", font=font(30),
           fill=(60, 50, 55))
    d.text((pad, 60), "上=マスター（文字なし） 中=ブログ用 下=note用",
           font=font(21, False), fill=(120, 105, 112))
    for i, (a, m, blog, note, _) in enumerate(rows):
        x = pad + (i % 3) * (tw + pad)
        y = 120 + (i // 3) * (th * 3 + 96 + pad)
        for j, p in enumerate((m, blog, note)):
            t = Image.open(p).convert("RGB")
            t.thumbnail((tw, th))
            cs.paste(t, (x, y + j * (th + 4)))
        d.text((x, y + th * 3 + 18),
               f"{a['post_id']}  "
               f"{'人物あり' if a['with_person'] else '人物なし'}",
               font=font(21), fill=(60, 50, 55))
        d.text((x, y + th * 3 + 44),
               a["lead_text"].replace("\n", " / ")[:26],
               font=font(19, False), fill=(120, 105, 112))
    cs.save(OUT / "CONTACT.jpg", "JPEG", quality=88)

    L = [f"# {len(rows)}本 検査結果 {stamp}\n\n",
         "**WordPressへは何も送っていない。**\n\n",
         "`—` は機械で判定しきれない項目。コンタクトシートを見て人が付ける。\n\n"]
    ids = [c[0] for c in rows[0][4]]
    L.append("| 項目 | " + " | ".join(str(a["post_id"]) for a, *_ in rows)
             + " |\n|---|" + "---|" * len(rows) + "\n")
    for k, cid in enumerate(ids):
        cells = []
        for *_, cl in rows:
            v = cl[k][1]
            cells.append("✅" if v is True else "❌" if v is False else "—")
        L.append(f"| {cid} | " + " | ".join(cells) + " |\n")
    L.append("\n## 項目の意味\n\n| 項目 | 見るもの |\n|---|---|\n")
    for cid, _, why in rows[0][4]:
        L.append(f"| {cid} | {why} |\n")
    ng = [(a["post_id"], cid) for a, *_, cl in rows
          for cid, v, _ in cl if v is False]
    L.append(f"\n## 再生成が必要なもの\n\n")
    if ng:
        L.append("| 記事 | 落ちた項目 |\n|---|---|\n")
        for pid, cid in ng:
            L.append(f"| {pid} | {cid} |\n")
    else:
        L.append("機械で見られる項目に落ちは無い。"
                 "`—` の項目をコンタクトシートで確認する。\n")
    (BATCH / "CHECKS.md").write_text("".join(L), encoding="utf-8")
    print(f"\n→ {OUT}/CONTACT.jpg\n→ {BATCH}/CHECKS.md")
    print("WordPressへの反映は、コンタクトシートの承認後。")


if __name__ == "__main__":
    main()
