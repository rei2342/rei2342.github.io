#!/usr/bin/env python3
"""
rewrite_uploader.py
workspace/rewrites/ にある検証済みのHTMLを、そのままWordPressへ反映する。

article_rewriter.py を LIVE で流すと本文を作り直してしまい、
人間が確認したものと別の記事が載ることになる。
確認したそのものを載せるために、生成と反映を分ける。

反映前にもう一度 audit() をかけ、落ちたものは触らない。
title も status も送らないので、タイトル・URL・公開状態は変わらない。
"""
import os
import re
import sys
import time
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings()

sys.path.insert(0, str(Path(__file__).parent))
import article_rewriter as _ar

WP_BASE = "https://sakura-eigo.com/wp-json/wp/v2"
WP_USER = "rei.00pt2342@gmail.com"
WP_PASS = os.environ.get("WP_APP_PASSWORD", "")
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"

SRC = Path("affiliate-research-engine/playbook/workspace/rewrites")
TARGET_IDS = [
    int(x) for x in os.environ.get("TARGET_IDS", "").replace(" ", "").split(",") if x
]


def find_file(post_id):
    hits = sorted(SRC.glob(f"{post_id}_*.html"))
    return hits[0] if hits else None


def update_post(post_id, content):
    r = requests.post(
        f"{WP_BASE}/posts/{post_id}",
        auth=(WP_USER, WP_PASS),
        json={"content": content},  # title/status/slug は送らない
        headers={"User-Agent": "Mozilla/5.0"},
        verify=False,
        timeout=60,
    )
    return r.status_code in (200, 201), r.status_code


def main():
    if not TARGET_IDS:
        print("TARGET_IDS が空。対象を指定してください。")
        sys.exit(1)

    print(f"{'DRY RUN' if DRY_RUN else 'LIVE'} — 対象 {len(TARGET_IDS)}件\n")
    report = [f"# Rewrite Upload Report\nMode: {'DRY RUN' if DRY_RUN else 'LIVE'}\n\n"]
    ok = skipped = failed = 0

    for pid in TARGET_IDS:
        path = find_file(pid)
        if not path:
            print(f"[{pid}] ✗ 生成物が見つからない")
            report.append(f"- [{pid}] NOT FOUND\n")
            failed += 1
            continue

        html = path.read_text(encoding="utf-8")
        # 先頭のコメント行（<!-- id | title | topic -->）は本文に含めない
        body = re.sub(r"^<!--.*?-->\s*", "", html, count=1, flags=re.DOTALL)

        issues = _ar.audit(body)
        if issues:
            print(f"[{pid}] ✗ 検査NG: {' / '.join(issues)} — 反映しない")
            report.append(f"- [{pid}] SKIPPED 検査NG: {' / '.join(issues)}\n")
            skipped += 1
            continue

        text_len = len(re.sub(r"<[^>]+>", "", body))
        print(f"[{pid}] 検査OK（{text_len}字, {path.name}）")

        if DRY_RUN:
            report.append(f"- [{pid}] DRY RUN（{text_len}字）\n")
            ok += 1
            continue

        done, code = update_post(pid, body)
        if done:
            print("   ✓ WP更新")
            report.append(f"- [{pid}] UPDATED（{text_len}字）\n")
            ok += 1
        else:
            print(f"   ✗ WP更新失敗 HTTP {code}")
            report.append(f"- [{pid}] WP FAILED HTTP {code}\n")
            failed += 1
        time.sleep(2)

    summary = f"\n## 集計\n- 反映: {ok}件\n- 検査NGで見送り: {skipped}件\n- 失敗: {failed}件\n"
    print(summary)
    report.append(summary)
    (SRC / "UPLOAD_REPORT.md").write_text("".join(report), encoding="utf-8")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
