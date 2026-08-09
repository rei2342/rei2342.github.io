#!/usr/bin/env python3
"""
social_spec.py
共通仕様 `config/social/sakura-social-v1.yaml` を読んで、
生成プロンプトと在庫の型へ変換する**アダプター**。

**このファイルに人物設定・文体・禁止事項・文字数を直接書かない。**
値はすべて YAML から読む。直書きが増えたら
`test_social_spec.py` の直書き検査が落ちる。

  python social_spec.py --platform x --article 521
出力: 標準出力（プロンプト本文）
"""
import argparse
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "config/social/sakura-social-v1.yaml"


def load_spec(path=SPEC_PATH):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _b(items, indent="- "):
    return "\n".join(f"{indent}{x}" for x in items)


def _persona(spec):
    p = spec["persona"]
    return ("あなたは" + p["name"] + "。\n"
            + " ".join(p["role"].split()) + "\n"
            + _b(p["voice"]) + "\n"
            + "**次は1つも書かない**（事実台帳に無いため）:\n"
            + _b(p["forbidden_self"]))


def _common(spec):
    s = spec["style"]
    f = spec["forbidden"]["patterns"]
    return ("守ること:\n" + _b(s["allow"])
            + "\n避けること:\n" + _b(s["avoid"])
            + "\nハッシュタグ: " + s["hashtag"]
            + "\n数字: " + s["numerals"]
            + "\n禁止:\n"
            + _b([x for group in f.values() for x in group]))


def _facts(spec):
    f = spec["facts"]
    return ("事実の扱い:\n"
            + _b([" ".join(f["rule"].split()),
                  " ".join(f["subset_of_article"].split()),
                  " ".join(f["regenerate_after_publish"].split())]))


def extraction_prompt(spec, article):
    """記事から4つの素材を抜く。XとThreadsで別の素材を使うための前段。"""
    e = spec["extraction"]
    return "\n\n".join([
        _persona(spec),
        "下の記事から、次の4つを抜き出す。**記事に書いてあることだけ**を使う。",
        "\n".join(f"- {k}: {v}" for k, v in e["fields"].items()),
        f"記事タイトル: {article['title']}\n記事URL: {article['url']}\n\n"
        f"記事本文:\n{article['body'][:6000]}",
        "【出力形式】このブロックだけ。説明不要。\n"
        + "\n".join(f"==={k.upper()}===\n（1〜2文）" for k in e["fields"]),
    ])


def x_prompt(spec, article, material):
    x = spec["x"]
    return "\n\n".join([
        _persona(spec),
        _facts(spec),
        "Xの投稿を1つ書く。目的は: " + x["purpose"],
        "組み立て:\n" + _b(x["structure"]),
        f"長さ: {x['length']['min']}〜{x['length']['max']}"
        f"（{x['length']['unit']}）。{x['lines']['min']}〜{x['lines']['max']}行。"
        f"空行は{x['blank_lines_max']}つまで。1投稿1論点。",
        f"URLは{x['url']['position']}に置く。"
        f"**URLだけの投稿・返信は作らない。**",
        f"絵文字は{spec['style']['emoji']['x']['min']}〜"
        f"{spec['style']['emoji']['x']['max']}個。"
        f"{spec['style']['emoji']['rule']}",
        _common(spec),
        "この記事から使う素材（**これ以外を足さない**）:\n"
        f"- 結論: {material['core_answer']}\n"
        f"- 今日できる確認: {material['one_check']}",
        f"記事タイトル: {article['title']}\n記事URL: {article['url']}",
        "**Threads用の文と同じ言い回しにしない。**",
        "【出力形式】本文だけ。URLは書かない（こちらで末尾に付ける）。説明不要。",
    ])


def threads_prompt(spec, article, material):
    t = spec["threads"]
    return "\n\n".join([
        _persona(spec),
        _facts(spec),
        "Threadsの投稿を書く。目的は: " + t["purpose"],
        f"原則{t['parts']['min']}〜{t['parts']['max']}投稿。"
        + " ".join(t["parts"]["rule"].split()),
        "1投稿目:\n" + _b(t["part1"]["must"])
        + "\nやらないこと:\n" + _b(t["part1"]["must_not"])
        + f"\n長さ {t['part1']['length']['min']}〜{t['part1']['length']['max']}字",
        "2投稿目:\n" + _b(t["part2"]["must"])
        + f"\n長さ {t['part2']['length']['min']}〜{t['part2']['length']['max']}字",
        f"段落は{t['sentences_per_paragraph']['min']}〜"
        f"{t['sentences_per_paragraph']['max']}文。"
        f"箇条書きは{t['bullets']['min']}〜{t['bullets']['max']}項目。\n"
        f"{t['line_length_rule']}\n句点は{t['kuten']}。",
        f"絵文字は{spec['style']['emoji']['threads']['min']}〜"
        f"{spec['style']['emoji']['threads']['max']}個。"
        f"{spec['style']['emoji']['rule']}",
        _common(spec),
        "この記事から使う素材（**これ以外を足さない**）:\n"
        f"- 読者の場面: {material['search_intent']}\n"
        f"- この記事にしかないもの: {material['unique_artifact']}",
        f"記事タイトル: {article['title']}\n記事URL: {article['url']}",
        "**X用の文と同じ言い回しにしない。**",
        "【出力形式】このブロックだけ。URLは書かない（こちらで付ける）。説明不要。\n"
        "===PART1===\n（1投稿目）\n===PART2===\n（2投稿目。"
        "1投稿で完結するなら空にする）",
    ])


def section(tag, text):
    m = re.search(rf"==={tag}===\s*(.*?)(?====[A-Z_0-9]+===|$)", text,
                  re.DOTALL)
    return m.group(1).strip() if m else ""


def with_utm(spec, url, platform):
    utm = spec[platform]["url"]["utm"]
    if utm in url:
        return url
    return url + ("&" if "?" in url else "?") + utm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", choices=["x", "threads", "extract"],
                    required=True)
    ap.add_argument("--article", required=True, help="記事ID")
    ap.add_argument("--posts-dir",
                    default=str(ROOT / "workspace/claims/posts"))
    ap.add_argument("--material", default="",
                    help="抽出済み素材のJSON")
    a = ap.parse_args()

    spec = load_spec()
    txt = Path(a.posts_dir) / f"{a.article}.txt"
    if not txt.exists():
        print(f"記事本文が無い: {txt}", file=sys.stderr)
        sys.exit(1)
    lines = txt.read_text(encoding="utf-8").split("\n")
    article = {"id": a.article, "title": lines[0].lstrip("# ").strip(),
               "url": lines[1].strip(), "body": "\n".join(lines[2:])}

    if a.platform == "extract":
        print(extraction_prompt(spec, article))
        return
    material = json.loads(a.material) if a.material else {
        k: f"（{k} をここに入れる）" for k in spec["extraction"]["fields"]}
    print(x_prompt(spec, article, material) if a.platform == "x"
          else threads_prompt(spec, article, material))


if __name__ == "__main__":
    main()
