#!/usr/bin/env python3
"""
seo_field_audit.py
本文を直しても、**表示側に旧設定が残る**場所を洗い出す。

本文だけ直して安心すると、検索結果とSNSのプレビューには
古いタイトルが出続ける。見る場所が違うので別に確認する。

  SEOタイトル / メタディスクリプション / OGP / 画像alt /
  アイキャッチのファイル名 / 構造化データ / パンくず / 関連記事カード

**画像の中の文字は自動で変えない。** 対象の一覧だけ出す。

  POSTS=286,235 python seo_field_audit.py
出力: workspace/seo/FIELD_AUDIT.md
"""
import os
import re
import sys
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
WP = "https://sakura-eigo.com/wp-json/wp/v2"
AUTH = ("rei.00pt2342@gmail.com", os.environ.get("WP_APP_PASSWORD", ""))
UA = {"User-Agent": "Mozilla/5.0"}
IDS = [x.strip() for x in os.environ.get("POSTS", "").split(",") if x.strip()]

STALE = re.compile(
    r"2[0-9]\s*歳|30歳まで|30歳になる前|あと\s*[0-9]+\s*年|残り\s*[0-9]+\s*年|"
    r"5年後回し|営業事務|さくらの英語挑戦記|さくらが確かめた|すべて無料|"
    r"▶\s*次の一手")

# 公開ページから抜く表示項目
FIELDS = [
    ("SEOタイトル", re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)),
    ("メタディスクリプション",
     re.compile(r'<meta[^>]+name="description"[^>]+content="([^"]*)"', re.I)),
    ("OGPタイトル",
     re.compile(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"', re.I)),
    ("OGP説明",
     re.compile(r'<meta[^>]+property="og:description"[^>]+content="([^"]*)"', re.I)),
    ("Twitterタイトル",
     re.compile(r'<meta[^>]+name="twitter:title"[^>]+content="([^"]*)"', re.I)),
    ("OGP画像",
     re.compile(r'<meta[^>]+property="og:image"[^>]+content="([^"]*)"', re.I)),
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    posts = _wa.published()
    if IDS:
        posts = [p for p in posts if str(p["id"]) in IDS]
    print(f"対象 {len(posts)}本")

    L = [f"# 表示項目に残る旧設定 {stamp}\n\n",
         "本文を直しても、検索結果とSNSのプレビューには古いタイトルが出続ける。\n"
         "見る場所が違うので別に確認する。\n\n",
         "**画像の中の文字は自動で変えない。** 対象の一覧だけ出す。\n\n"]

    bad, imgs, ok = [], [], 0
    for p in posts:
        pid, link = p["id"], p.get("link", "")
        hits = []
        try:
            r = requests.get(link, headers=UA, verify=False, timeout=45)
            html = r.text if r.status_code == 200 else ""
        except Exception as e:
            L.append(f"- 記事{pid}: 取得できず（{type(e).__name__}）\n")
            continue

        for name, rx in FIELDS:
            m = rx.search(html)
            if not m:
                continue
            val = re.sub(r"\s+", " ", _q.strip_tags(m.group(1))).strip()
            if STALE.search(val):
                hits.append((name, val[:110]))

        # 画像の alt とファイル名
        for m in re.finditer(r"<img[^>]+>", html):
            tag = m.group(0)
            alt = re.search(r'alt="([^"]*)"', tag)
            src = re.search(r'src="([^"]*)"', tag)
            if alt and STALE.search(alt.group(1)):
                hits.append(("画像alt", alt.group(1)[:110]))
            if src and STALE.search(src.group(1)):
                hits.append(("画像ファイル名", src.group(1)[-80:]))

        # 構造化データ・パンくず
        for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>',
                             html, re.S | re.I):
            for s in STALE.findall(m.group(1)):
                hits.append(("構造化データ", s))

        # 関連記事カード（他記事の旧タイトルがここに出る）
        for m in re.finditer(r'class="[^"]*(?:related|carditem|entry-card)[^"]*"[^>]*>'
                             r'(.{0,600}?)</a>', html, re.S | re.I):
            t = _q.strip_tags(m.group(1))
            for s in STALE.findall(t):
                hits.append(("関連記事カード", s))

        # アイキャッチの中の文字は機械で読めない。目視の対象として出す
        og = FIELDS[5][1].search(html)
        if og:
            imgs.append((pid, og.group(1)))

        if hits:
            bad.append((pid, link, hits))
        else:
            ok += 1
        print(f"[{pid}] {'⚠️ ' + str(len(hits)) + '件' if hits else '✅'}")

    L.append(f"## 結果\n\n- 旧設定が残る記事: **{len(bad)}本**\n"
             f"- 問題なし: {ok}本\n\n")
    if bad:
        L.append("| 記事 | 場所 | 値 |\n|---|---|---|\n")
        for pid, link, hits in bad:
            seen = set()
            for name, val in hits:
                if (name, val) in seen:
                    continue
                seen.add((name, val))
                L.append(f"| {pid} | {name} | {val.replace('|', '｜')} |\n")

    L.append("\n## アイキャッチ画像（中の文字は目視で確認）\n\n"
             "**自動で変えない。** タイトルを変えた記事の画像に旧設定の文字が\n"
             "焼き込まれていないかを、人が開いて確認する。\n\n"
             "| 記事 | 画像URL |\n|---|---|\n")
    for pid, url in imgs:
        L.append(f"| {pid} | {url} |\n")

    (OUT / "FIELD_AUDIT.md").write_text("".join(L), encoding="utf-8")
    print(f"\n旧設定が残る {len(bad)}本 → workspace/seo/FIELD_AUDIT.md")


if __name__ == "__main__":
    main()
