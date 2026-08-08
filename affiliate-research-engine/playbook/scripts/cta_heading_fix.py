#!/usr/bin/env python3
"""
cta_heading_fix.py
公開記事のCTAボックスの**見出しだけ**を差し替える。

対象は「▶ さくらが確かめた・次の一手（すべて無料）」。
2026-08-09に生成側を直したが、すでに出ている記事には残っている。

  - 「さくらが確かめた」… 台帳に無い一人称の行動
  - 「すべて無料」    … 箱に入る全案件への一括訴求

**リンクは1文字も触らない。** 見出しの1行だけを置き換える。
ここは「同じ30歳でも意味が3つある」旧ペルソナ設定とは違って、
文言が1種類しかないので機械で置いてよい。

  DRY_RUN=false python cta_heading_fix.py
出力: workspace/backups/<日付>/cta_heading/<id>.json / CTA_HEADING.md
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
import affiliate_inserter as _ai
import quality_rules as _q
import wp_audit as _wa

JST = timezone(timedelta(hours=9))
WP = "https://sakura-eigo.com/wp-json/wp/v2"
WP_USER = "rei.00pt2342@gmail.com"
WP_PASS = os.environ.get("WP_APP_PASSWORD", "")
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"
BK = Path("affiliate-research-engine/playbook/workspace/backups")
UA = {"User-Agent": "Mozilla/5.0"}
AUTH = (WP_USER, WP_PASS)

# 差し替える見出し。表記ゆれを許すが、**箱の見出しの行だけ**に限る
OLD_HEADING = re.compile(
    r"(<p[^>]*>)\s*▶?\s*さくらが確かめた[^<]*?(?:</p>)",
    re.IGNORECASE)

# 見出しの外に「すべて無料」だけが残っている場合
BLANKET = re.compile(r"（\s*すべて無料\s*）|\(\s*すべて無料\s*\)")


def fix(html):
    """見出しを差し替えた本文と、当たった数を返す。"""
    n = 0

    def rep(m):
        nonlocal n
        n += 1
        return f"{m.group(1)}{_ai.CTA_HEADING}</p>"

    out = OLD_HEADING.sub(rep, html)
    out, k = BLANKET.subn("", out)
    return out, n, k


def main():
    day = datetime.now(JST).strftime("%Y-%m-%d")
    (BK / day / "cta_heading").mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    L = [f"# CTAボックスの見出し差し替え {stamp}\n\n",
         f"モード: **{'DRY RUN（書いていない）' if DRY_RUN else 'LIVE（書いた）'}**\n\n",
         "旧: `▶ さくらが確かめた・次の一手（すべて無料）`\n\n",
         f"新: `{_ai.CTA_HEADING}`\n\n",
         "**リンクは1文字も触らない。** 見出しの1行だけを置き換える。\n\n"]

    posts = _wa.published()
    print(f"公開記事 {len(posts)}本")
    L.append("| 記事 | 見出し | 「すべて無料」 | 結果 | 差し替え後のゲート |\n"
             "|---|---|---|---|---|\n")

    hit_posts = 0
    for p in posts:
        pid = p["id"]
        g = requests.get(f"{WP}/posts/{pid}", auth=AUTH, headers=UA,
                         params={"context": "edit"}, verify=False, timeout=45)
        if g.status_code != 200:
            L.append(f"| {pid} | — | — | ❌ 取得できず HTTP {g.status_code} | — |\n")
            continue
        raw = g.json()["content"]["raw"]
        new, n, k = fix(raw)
        if not (n or k):
            continue
        hit_posts += 1

        (BK / day / "cta_heading" / f"{pid}.json").write_text(
            json.dumps({"id": pid, "checked_at": stamp, "content_raw": raw},
                       ensure_ascii=False, indent=2), encoding="utf-8")

        # 差し替えたあとに、箱のゲートが通ることを確かめる
        left = _q.cta_box_text_gate(new)
        gate = "✅ 0件" if not left else f"⚠️ {len(left)}件 残る: {left[0]['reason']}"

        if DRY_RUN:
            L.append(f"| {pid} | {n} | {k} | （DRY RUN） | {gate} |\n")
            print(f"[{pid}] 見出し{n} すべて無料{k} （DRY RUN） {gate}")
            continue

        up = requests.post(f"{WP}/posts/{pid}", auth=AUTH, headers=UA,
                           verify=False, timeout=60, json={"content": new})
        ok = up.status_code in (200, 201)
        L.append(f"| {pid} | {n} | {k} | "
                 f"{'✅ 差し替えた' if ok else '❌ ' + str(up.status_code)} | {gate} |\n")
        print(f"[{pid}] 見出し{n} すべて無料{k} {'OK' if ok else up.status_code} {gate}")

    L.append(f"\n**{hit_posts}本**に旧見出しが残っていた。\n\n")
    L.append(f"バックアップ: `workspace/backups/{day}/cta_heading/<記事ID>.json`\n\n")
    L.append("戻すときは、このJSONの `content_raw` をそのまま書き戻す。\n")

    (BK / day / "CTA_HEADING.md").write_text("".join(L), encoding="utf-8")
    print(f"\n{hit_posts}本 → workspace/backups/{day}/CTA_HEADING.md")


if __name__ == "__main__":
    main()
