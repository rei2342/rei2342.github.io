#!/usr/bin/env python3
"""
eyecatch_spec.py
共通仕様 `config/eyecatch/sakura-v1.yaml` を読んで、
画像AIへ渡すプロンプトへ変換する**アダプター**。

**このファイルに人物設定・画風・禁止事項・比率を直接書かない。**
値はすべて YAML から読む。直書きが増えたら
`test_eyecatch_spec.py` の直書き検査が落ちる。

TypeScript側（lib/eyecatchPrompt.ts）は同じ YAML を読んで
同じ文字列を返す。差が出たら差分検出テストが落ちる。

  python eyecatch_spec.py --article 993
出力: 標準出力（プロンプト本文）
"""
import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "config/eyecatch/sakura-v1.yaml"


def load_spec(path=SPEC_PATH):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def load_articles(path):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _bullets(items, indent="- "):
    return "\n".join(f"{indent}{x}" for x in items)


def build_prompt(spec, article, category):
    """マスター画像（文字なし）のプロンプトを組み立てる。

    段落の順番と見出しは TypeScript 側と揃える。ここを変えたら
    向こうも変わる（同じ YAML と同じ順番で組み立てているため）。
    """
    c = spec["character"]
    s = spec["style"]
    comp = spec["composition"]
    neg = spec["negative_prompt"]
    colors = spec["category_colors"]
    # 記事に category があればそちらを使う。20本は記事ごとに違う
    accent = colors.get(article.get("category", category), colors["_default"])
    w, h = spec["master_size"]
    box = comp["text_safe_area"]["box"]

    fixed = c["fixed"]
    parts = []

    parts.append(
        "CHARACTER (identical in every image of this site):\n"
        + _bullets([
            fixed["ethnicity"],
            fixed["age_impression"],
            fixed["head_body_ratio"],
            f'{fixed["hair_length"]}, {fixed["hair_color"]}, '
            f'{fixed["hair_texture"]}',
            fixed["signature_accessory"],
            f'{fixed["clothing_base"]}, {fixed["clothing_accent"]}',
            fixed["expression"],
            fixed["eye_treatment"],
        ]))

    parts.append(
        "CHARACTER MUST NOT:\n" + _bullets(c["forbidden"]))

    parts.append(
        "STYLE:\n"
        + _bullets([
            s["medium"], s["linework"], s["shading"], s["light"],
            "base palette: " + ", ".join(s["base_colors"]),
            "saturation: " + s["saturation"],
        ])
        + "\nNever: " + "; ".join(s["forbidden"]))

    parts.append(
        f"COMPOSITION:\n"
        + _bullets([
            f"canvas exactly {w} x {h} px, {spec['master_aspect_ratio']}",
            f"place the subject {comp['subject_anchor']}",
            f"keep the rectangle x={box[0]}-{box[2]}, y={box[1]}-{box[3]} "
            f"free of the subject and of strong contrast "
            f"({comp['text_safe_area']['rule']})",
            comp["note_crop_safe"]["rule"],
            f"keep {comp['edge_margin_px']}px clear on every edge",
            comp["scene_rule"],
        ]))

    person = ("Show the character." if article.get("with_person")
              else "Do NOT show any person. Objects, hands or the place only.")
    parts.append(
        "THIS ARTICLE:\n"
        + _bullets([
            person,
            f"camera: {article['camera_distance']}",
            "expression: " + " ".join(article["expression"].split()),
            "pose: " + " ".join(article["pose"].split()),
            "props: " + ", ".join(article["props"]),
            "background: " + article["background"],
            "colour: " + " ".join(article["palette"].split()),
            f"accent colour: {accent['name']} ({accent['hex']}), "
            f"used on one small object only",
            "scene: " + " ".join(article["scene"].split()),
            "what makes this image different from the others: "
            + " ".join(article["uniqueness_reason"].split()),
        ]))

    # 参照画像の使い分け。**3枚を均等に混ぜない**ので、
    # どれから何を採るかを毎回そのまま渡す
    ref = spec["reference_assets"]["directive"]
    parts.append(
        "REFERENCES:\n"
        + (ref["with_person"] if article.get("with_person")
           else ref["without_person"]).strip())

    parts.append(
        "DO NOT INCLUDE:\n" + _bullets(neg["forbidden_content"])
        + "\n" + neg["always_append"])

    return "\n\n".join(parts)


def build_overlay_plan(spec, article, category):
    """ブログ用の文字合成の指示（画像AIには渡さない）。"""
    t = spec["text_overlay"]
    accent = spec["category_colors"].get(
        article.get("category", category), spec["category_colors"]["_default"])
    return {
        "size": spec["blog_export"]["size"],
        "lead": {"text": article["lead_text"], **t["lead"]},
        "sub": {"text": article["sub_text"], **t["sub"]},
        "accent_hex": accent["hex"],
        "font_family": t["font_family"],
        "filename": article["filename"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", default=str(SPEC_PATH))
    ap.add_argument("--articles",
                    default=str(ROOT / "config/eyecatch/"
                                       "articles-ai-cluster.yaml"))
    ap.add_argument("--article", required=True,
                    help="post_id または slug")
    ap.add_argument("--json", action="store_true",
                    help="プロンプトと合成計画をJSONで出す")
    a = ap.parse_args()

    spec = load_spec(a.spec)
    doc = load_articles(a.articles)
    art = next((x for x in doc["articles"]
                if str(x["post_id"]) == a.article or x["slug"] == a.article),
               None)
    if not art:
        print(f"記事が見つからない: {a.article}", file=sys.stderr)
        sys.exit(1)

    prompt = build_prompt(spec, art, doc["category"])
    if a.json:
        print(json.dumps({
            "prompt": prompt,
            "overlay": build_overlay_plan(spec, art, doc["category"]),
        }, ensure_ascii=False, indent=2))
    else:
        print(prompt)


if __name__ == "__main__":
    main()
