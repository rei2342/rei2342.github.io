#!/usr/bin/env python3
"""
title_fix.py
特定の記事IDのタイトルを、指定した文字列にそのまま差し替える。

title_rewriter の一括生成で不具合が出た分の手当てや、
人間が決めたタイトルを反映するのに使う。
対象は workspace/title_rewrites/fixes.json（{"記事ID": "新しいタイトル"}）。
スラッグは送らないのでURLは変わらない。
"""
import json
import os
import time
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings()

WP_BASE = "https://sakura-eigo.com/wp-json/wp/v2"
WP_USER = "rei.00pt2342@gmail.com"
WP_PASS = os.environ.get("WP_APP_PASSWORD", "")
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"

BASE = Path("affiliate-research-engine/playbook/workspace/title_rewrites")
FIXES = BASE / "fixes.json"


def get_title(post_id):
    r = requests.get(
        f"{WP_BASE}/posts/{post_id}",
        auth=(WP_USER, WP_PASS),
        params={"_fields": "id,title"},
        headers={"User-Agent": "Mozilla/5.0"},
        verify=False,
        timeout=30,
    )
    return r.json().get("title", {}).get("rendered", "") if r.status_code == 200 else None


def update_title(post_id, new_title):
    r = requests.post(
        f"{WP_BASE}/posts/{post_id}",
        auth=(WP_USER, WP_PASS),
        json={"title": new_title},
        headers={"User-Agent": "Mozilla/5.0"},
        verify=False,
        timeout=30,
    )
    return r.status_code in (200, 201)


def main():
    fixes = json.loads(FIXES.read_text(encoding="utf-8"))
    print(f"{'DRY RUN' if DRY_RUN else 'LIVE'} — 対象 {len(fixes)}件\n")

    report = [f"# Title Fix Report\nMode: {'DRY RUN' if DRY_RUN else 'LIVE'}\n\n"]
    ok = ng = 0

    for pid, new_title in fixes.items():
        current = get_title(pid)
        if current is None:
            print(f"[{pid}] ✗ 取得失敗")
            report.append(f"- [{pid}] FETCH FAILED\n")
            ng += 1
            continue

        print(f"[{pid}]")
        print(f"   旧: {current}")
        print(f"   新: {new_title}")
        report.append(f"\n### [{pid}]\n- 旧: {current}\n- **新: {new_title}**\n")

        if DRY_RUN:
            ok += 1
            continue

        if update_title(pid, new_title):
            print("   ✓ 更新")
            report.append("- 更新: OK\n")
            ok += 1
        else:
            print("   ✗ 更新失敗")
            report.append("- 更新: FAILED\n")
            ng += 1
        time.sleep(1)

    summary = f"\n## 集計\n- 成功: {ok}件\n- 失敗: {ng}件\n"
    print(summary)
    report.append(summary)
    (BASE / "FIX_REPORT.md").write_text("".join(report), encoding="utf-8")


if __name__ == "__main__":
    main()
