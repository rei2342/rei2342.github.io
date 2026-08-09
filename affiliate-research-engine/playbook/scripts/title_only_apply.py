#!/usr/bin/env python3
"""
title_only_apply.py
**タイトルだけ**を差し替える。本文には触らない。

内部リンクを入れたあとに本文ごと再反映すると、リンクが消える。
タイトルの直しだけが要るときは、これを使う。

  DRY_RUN=false POSTS=273,150 python title_only_apply.py
出力: workspace/backups/<日付>/titles/<id>.json / TITLE_APPLY.md
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
JST = timezone(timedelta(hours=9))
WP = "https://sakura-eigo.com/wp-json/wp/v2"
AUTH = ("rei.00pt2342@gmail.com", os.environ.get("WP_APP_PASSWORD", ""))
UA = {"User-Agent": "Mozilla/5.0"}
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"
POSTS = [x.strip() for x in os.environ.get("POSTS", "").split(",") if x.strip()]
TITLES = Path("affiliate-research-engine/playbook/workspace/claims/rewrites/TITLES.json")
BK = Path("affiliate-research-engine/playbook/workspace/backups")


def main():
    day = datetime.now(JST).strftime("%Y-%m-%d")
    (BK / day / "titles").mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    titles = json.loads(TITLES.read_text(encoding="utf-8"))

    L = [f"# タイトルだけの差し替え {stamp}\n\n",
         f"モード: **{'DRY RUN' if DRY_RUN else 'LIVE'}**\n\n",
         "**本文には触らない。** 内部リンクを消さないため。\n\n",
         "| 記事 | 前 | 後 | 結果 |\n|---|---|---|---|\n"]
    for pid in POSTS:
        want = titles.get(pid)
        if not want:
            L.append(f"| {pid} | — | — | TITLES.json に無い |\n")
            continue
        g = requests.get(f"{WP}/posts/{pid}", auth=AUTH, headers=UA,
                         params={"context": "edit"}, verify=False, timeout=45)
        if g.status_code != 200:
            L.append(f"| {pid} | — | — | ❌ 取得できず {g.status_code} |\n")
            continue
        cur = g.json()["title"]["raw"]
        (BK / day / "titles" / f"{pid}.json").write_text(
            json.dumps({"id": pid, "checked_at": stamp, "title_raw": cur},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        if cur == want:
            L.append(f"| {pid} | {cur[:34]} | 変更なし | — |\n")
            continue
        if DRY_RUN:
            L.append(f"| {pid} | {cur[:34]} | {want[:34]} | （DRY RUN） |\n")
            print(f"[{pid}] {cur[:30]} → {want[:30]}（DRY RUN）")
            continue
        up = requests.post(f"{WP}/posts/{pid}", auth=AUTH, headers=UA,
                           verify=False, timeout=60, json={"title": want})
        ok = up.status_code in (200, 201)
        L.append(f"| {pid} | {cur[:34]} | {want[:34]} | "
                 f"{'✅' if ok else '❌ ' + str(up.status_code)} |\n")
        print(f"[{pid}] {'OK' if ok else up.status_code}")

    (BK / day / "TITLE_APPLY.md").write_text("".join(L), encoding="utf-8")
    print(f"\n→ workspace/backups/{day}/TITLE_APPLY.md")


if __name__ == "__main__":
    main()
