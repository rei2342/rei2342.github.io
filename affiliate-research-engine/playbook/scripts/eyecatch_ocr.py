#!/usr/bin/env python3
"""
eyecatch_ocr.py
アイキャッチ画像を実際に取得して、**画像の中の文字をOCRで読む。**

「機械で読めない」で止めると、本文から消したはずの数字が画像に
焼き込まれたまま残る。tesseract（日本語＋英語）で読んで、
本文と矛盾する語を一覧にする。

**自動で差し替えない。** 差し替え案まで作って、人が判断する。

  python eyecatch_ocr.py
出力: workspace/seo/EYECATCH_OCR.md / .csv
"""
import csv
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings()
sys.path.insert(0, str(Path(__file__).parent))
import quality_rules as _q
import wp_audit as _wa

OUT = Path("affiliate-research-engine/playbook/workspace/seo")
JST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0"}

# 画像の中にあったら困るもの
BAD = [
    ("旧年齢", re.compile(r"2[0-9]\s*歳|3[0-9]\s*歳|27|28|30代")),
    # 「515 515 515」のように点が付かない素のスコアも拾う。
    # OCRは「点」を落としやすいので、TOEICの取りうる範囲の3桁を見る
    ("TOEICスコア", re.compile(r"[3-9][0-9]{2}\s*点|\b(?:[4-9][0-9]5|[4-9][0-9]0)\b")),
    ("金額", re.compile(r"[0-9][0-9,]*\s*円|[0-9]+\s*万円")),
    ("期間", re.compile(r"[0-9]+\s*(?:日|週間|ヶ月|か月|カ月|年)|"
                        r"[0-9]+\s*days?\b|\bdays\b")),
    ("削除済みの結果", re.compile(r"成功|伸びた|改善|達成|できた|突破|クリア")),
    ("旧サイト名", re.compile(r"さくらの英語挑戦記|英語挑戦記")),
]

# サービス名。本文に無いサービスが画像に出ていたら矛盾
# OCRはイラストの線を英字に読み違える。**3文字以上の名前だけ**を見る。
# 「QQ」のような2文字はノイズと区別が付かないので入れない
SERVICES = ("speek", "スパトレ", "DMM英会話", "ネイティブキャンプ",
            "QQ English", "レアジョブ", "スタディサプリ", "Notta",
            "U-GAKU", "留学情報館", "CEBRIDGE")


def ocr(path):
    """日本語＋英語で読む。tesseract が無ければ空を返す。"""
    try:
        r = subprocess.run(
            ["tesseract", str(path), "stdout", "-l", "jpn+eng", "--psm", "11"],
            capture_output=True, text=True, timeout=120)
        return re.sub(r"\s+", " ", r.stdout).strip()
    except FileNotFoundError:
        return "__NO_TESSERACT__"
    except Exception as e:
        return f"__ERROR__{type(e).__name__}"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    posts = _wa.published()
    tmp = Path(tempfile.mkdtemp())
    print(f"公開記事 {len(posts)}本")

    rows = []
    for p in sorted(posts, key=lambda x: x["id"]):
        pid = str(p["id"])
        title = re.sub(r"<[^>]+>", "", p["title"]["rendered"])
        body = _q.strip_tags(p.get("content", {}).get("rendered", ""))
        link = p.get("link", "")

        # アイキャッチのURLを取る
        img = ""
        mid = p.get("featured_media")
        if mid:
            try:
                m = requests.get(
                    f"https://sakura-eigo.com/wp-json/wp/v2/media/{mid}",
                    headers=UA, verify=False, timeout=40)
                if m.status_code == 200:
                    img = m.json().get("source_url", "")
            except Exception:
                pass
        if not img:
            rows.append({"post_id": pid, "title": title[:40], "url": link,
                         "image": "", "ocr": "", "problems": "画像なし",
                         "conflict": "", "action": "アイキャッチを設定する"})
            print(f"[{pid}] 画像なし")
            continue

        # 取得してOCR
        text = ""
        try:
            r = requests.get(img, headers=UA, verify=False, timeout=60)
            if r.status_code == 200:
                f = tmp / f"{pid}.png"
                f.write_bytes(r.content)
                text = ocr(f)
        except Exception as e:
            text = f"__ERROR__{type(e).__name__}"

        if text.startswith("__NO_TESSERACT__"):
            print("tesseract が入っていない。ワークフローで apt install が要る")
            text = ""

        probs = []
        for label, rx in BAD:
            for hit in set(rx.findall(text)):
                probs.append(f"{label}:{hit}")
        # 本文に無いサービス名が画像に出ていないか
        conflicts = [s for s in SERVICES if s.lower() in text.lower()
                     and s not in body]
        # ファイル名の手掛かりも見る
        fname = img.rsplit("/", 1)[-1]
        fn_hint = re.findall(r"\d{2,3}-?days?|success|\d{3}|27|90", fname)

        action = ""
        if probs or conflicts:
            action = "**差し替え候補。** 画像内の文字を本文と揃える"
        elif fn_hint:
            action = "ファイル名に古い語。画像の中身は問題なし。名前だけ変える"

        rows.append({
            "post_id": pid, "title": title[:40], "url": link, "image": img,
            "ocr": text[:200], "problems": " / ".join(probs) or "なし",
            "conflict": " / ".join(conflicts) or "なし", "action": action,
        })
        print(f"[{pid}] OCR{len(text)}字 問題{len(probs)} 矛盾{len(conflicts)}")

    bad = [r for r in rows if r["action"]]
    L = [f"# アイキャッチ画像の実物監査（OCR） {stamp}\n\n",
         f"公開 **{len(rows)}本**の画像を実際に取得して、tesseract（日本語＋英語）で読んだ。\n\n",
         f"- **差し替え候補: {sum(1 for r in rows if r['problems'] != 'なし' or r['conflict'] != 'なし')}本**\n",
         f"- ファイル名だけ古い: {sum(1 for r in rows if r['action'].startswith('ファイル名'))}本\n",
         f"- 問題なし: {sum(1 for r in rows if not r['action'])}本\n\n",
         "**自動で差し替えていない。**\n\n---\n\n",
         "| 記事 | 画像 | 画像内の文字（OCR） | 見つかった語 | 本文との矛盾 | 推奨対応 |\n",
         "|---|---|---|---|---|---|\n"]
    for r in bad:
        L.append(f"| [{r['post_id']}]({r['url']}) | {r['image'].rsplit('/', 1)[-1]} | "
                 f"{r['ocr'][:70].replace('|', '｜')} | {r['problems'][:60]} | "
                 f"{r['conflict']} | {r['action']} |\n")
    if not bad:
        L.append("| — | — | — | — | — | 問題なし |\n")

    L.append("\n---\n\n## 全記事のOCR結果\n\n"
             "| 記事 | 画像 | 画像内の文字 |\n|---|---|---|\n")
    for r in rows:
        L.append(f"| {r['post_id']} | {r['image'].rsplit('/', 1)[-1]} | "
                 f"{(r['ocr'] or '（文字なし）')[:80].replace('|', '｜')} |\n")

    with open(OUT / "EYECATCH_OCR.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    (OUT / "EYECATCH_OCR.md").write_text("".join(L), encoding="utf-8")
    print(f"\n差し替え候補 {len(bad)}本 → workspace/seo/EYECATCH_OCR.md")


if __name__ == "__main__":
    main()
