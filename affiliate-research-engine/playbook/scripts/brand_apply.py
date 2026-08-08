#!/usr/bin/env python3
"""
brand_apply.py
サイト名・キャッチフレーズ・カテゴリを反映する。**戻せる形でしか書かない。**

やること:
  1. 現在の設定を丸ごとバックアップ
  2. サイトタイトルとキャッチフレーズを更新
  3. 新カテゴリを**新規作成**（既存カテゴリは消さない・URLも変えない）
  4. 旧表現の残存を全記事・設定から検索

**カテゴリのslugは既存のものを一切変更しない。** 変えると301が要る。
新規に作って、記事を後から移すだけにする。

  DRY_RUN=false python brand_apply.py
出力: workspace/backups/<日付>/brand.json / BRAND_APPLY.md
"""
import json
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

JST = timezone(timedelta(hours=9))
SITE = "https://sakura-eigo.com"
WP_BASE = f"{SITE}/wp-json/wp/v2"
WP_USER = "rei.00pt2342@gmail.com"
WP_PASS = os.environ.get("WP_APP_PASSWORD", "")
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"
BK = Path("affiliate-research-engine/playbook/workspace/backups")
UA = {"User-Agent": "Mozilla/5.0"}

NEW_TITLE = "さくらの大人英語学び直しガイド"
NEW_TAGLINE = "働きながら英語をやり直したい人へ"

# 新しく作るカテゴリ。**既存のslugは触らない**
NEW_CATS = [
    ("勉強法・続け方", "study-method", "続かない理由を、意志ではなく形から見直す"),
    ("TOEIC・スコア", "toeic-score", "止まったスコアの内訳を分解して、次に直す場所を決める"),
    ("サービスの選び方", "service-choice", "アプリ・オンライン英会話・コーチングの比べ方"),
    ("AI英語学習", "ai-english", "AI翻訳・ChatGPT・AI英会話をどう使うか"),
    ("留学・ワーホリ", "study-abroad", "費用の出し方、エージェントの選び方、制度の確認"),
]

# 消したい旧表現。全記事と設定から探す
STALE = [
    ("旧サイト名", r"さくらの英語挑戦記"),
    ("年齢の明示", r"27\s*歳"),
    ("期限の宣言", r"30歳まで|あと\s*3\s*年|残り\s*3\s*年"),
    ("未確認の経歴", r"5年後回し|英語を5年|営業事務"),
]


def main():
    day = datetime.now(JST).strftime("%Y-%m-%d")
    (BK / day).mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    L = [f"# ブランド反映 {stamp}\n\n",
         f"モード: **{'DRY RUN（書いていない）' if DRY_RUN else 'LIVE（書いた）'}**\n\n"]

    # ── 1. 設定のバックアップ ─────────────────────────
    r = requests.get(f"{SITE}/wp-json", headers=UA, verify=False, timeout=40)
    pub = r.json() if r.status_code == 200 else {}
    s = requests.get(f"{WP_BASE}/settings", auth=(WP_USER, WP_PASS),
                     headers=UA, verify=False, timeout=40)
    settings = s.json() if s.status_code == 200 else {}
    cats = requests.get(f"{WP_BASE}/categories", auth=(WP_USER, WP_PASS),
                        params={"per_page": 100}, headers=UA, verify=False,
                        timeout=40)
    cat_list = cats.json() if cats.status_code == 200 else []

    (BK / day / "brand.json").write_text(json.dumps({
        "checked_at": stamp,
        "public_name": pub.get("name"), "public_description": pub.get("description"),
        "settings": settings,
        "categories": [{"id": c["id"], "name": c["name"], "slug": c["slug"],
                        "count": c.get("count")} for c in cat_list],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    L.append("## 反映前の状態（バックアップ済み）\n\n")
    L.append(f"- サイト名: **{pub.get('name')}**\n")
    L.append(f"- キャッチフレーズ: **{pub.get('description') or '（空）'}**\n")
    L.append(f"- カテゴリ: {len(cat_list)}件 "
             f"（{', '.join(c['name'] for c in cat_list[:8])}）\n")
    L.append(f"- バックアップ: `workspace/backups/{day}/brand.json`\n\n")
    print(f"サイト名: {pub.get('name')}")
    print(f"キャッチ: {pub.get('description')}")
    print(f"カテゴリ: {[c['name'] for c in cat_list]}")

    # ── 2. サイト名とキャッチフレーズ ────────────────────
    L.append("## サイト名とキャッチフレーズ\n\n")
    L.append(f"| 項目 | 前 | 後 |\n|---|---|---|\n")
    L.append(f"| サイト名 | {pub.get('name')} | **{NEW_TITLE}** |\n")
    L.append(f"| キャッチフレーズ | {pub.get('description') or '（空）'} "
             f"| **{NEW_TAGLINE}** |\n\n")
    if not DRY_RUN:
        up = requests.post(f"{WP_BASE}/settings", auth=(WP_USER, WP_PASS),
                           headers=UA, verify=False, timeout=40,
                           json={"title": NEW_TITLE, "description": NEW_TAGLINE})
        ok = up.status_code in (200, 201)
        L.append(f"→ {'✅ 反映した' if ok else '❌ ' + str(up.status_code) + ' ' + up.text[:150]}\n\n")
        print(f"設定更新: {'OK' if ok else up.status_code}")
    else:
        L.append("→ （DRY RUN）\n\n")

    # ── 3. カテゴリを新規作成（既存は触らない）───────────
    have = {c["slug"]: c for c in cat_list}
    L.append("## カテゴリ\n\n**既存カテゴリのslugは1つも変更しない。**\n"
             "新規に作るだけなので、既存URLは動かない。301も不要。\n\n")
    L.append("| 名前 | slug | 状態 |\n|---|---|---|\n")
    for name, slug, desc in NEW_CATS:
        if slug in have:
            L.append(f"| {name} | `{slug}` | すでにある（ID {have[slug]['id']}） |\n")
            print(f"[cat] {slug} 既存")
            continue
        if DRY_RUN:
            L.append(f"| {name} | `{slug}` | 新規作成する（DRY RUN） |\n")
            continue
        cr = requests.post(f"{WP_BASE}/categories", auth=(WP_USER, WP_PASS),
                           headers=UA, verify=False, timeout=40,
                           json={"name": name, "slug": slug, "description": desc})
        ok = cr.status_code in (200, 201)
        L.append(f"| {name} | `{slug}` | "
                 f"{'✅ 作成（ID ' + str(cr.json().get('id')) + '）' if ok else '❌ ' + str(cr.status_code)} |\n")
        print(f"[cat] {slug} {'作成' if ok else cr.status_code}")

    # ── 4. 旧表現の残存検索 ─────────────────────────
    L.append("\n## 旧表現の残存\n\n")
    posts = _wa.published()
    hay = {"（サイト名）": str(pub.get("name", "")),
           "（キャッチフレーズ）": str(pub.get("description", ""))}
    total = 0
    for label, pat in STALE:
        rx = re.compile(pat)
        hits = []
        for k, v in hay.items():
            if rx.search(v):
                hits.append(k)
        for p in posts:
            txt = _q.strip_tags(p.get("content", {}).get("rendered", "")) \
                  + re.sub(r"<[^>]+>", "", p["title"]["rendered"])
            n = len(rx.findall(txt))
            if n:
                hits.append(f"記事{p['id']}({n})")
        total += len(hits)
        L.append(f"### {label} `{pat}`\n\n")
        L.append(f"- 残存 **{len(hits)}箇所**"
                 + (f": {' '.join(hits[:25])}" if hits else "（なし）") + "\n\n")
        print(f"[{label}] {len(hits)}箇所")

    L.append(f"\n**残存の合計 {total}箇所**\n\n")
    L.append("記事側は改修で消えているものが多い。残っているのは未改修の記事と、\n"
             "**ウィジェット・フッター・OGPなど、REST APIから見えない場所**の可能性がある。\n"
             "そこは管理画面で目視する。\n")

    (BK / day / "BRAND_APPLY.md").write_text("".join(L), encoding="utf-8")
    print(f"\n→ workspace/backups/{day}/BRAND_APPLY.md")


if __name__ == "__main__":
    main()
