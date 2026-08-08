#!/usr/bin/env python3
"""
wp_publisher.py
下書きを公開する。公開は取り消しの効きにくい操作なので、
出す前に最低限の条件を機械で確かめてから status を切り替える。

確認すること:
  - 内部メモ（【Threads用】等）ではない
  - アイキャッチ画像が設定されている
  - カテゴリが未分類のままでない
  - 本文が十分な長さある
  - CTAボックスが入っている
一つでも欠ければ公開しない（公開してから直すより手戻りが小さい）。
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
import quality_rules as _q

WP_BASE = "https://sakura-eigo.com/wp-json/wp/v2"
WP_USER = "rei.00pt2342@gmail.com"
WP_PASS = os.environ.get("WP_APP_PASSWORD", "")
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"
MIN_CHARS = int(os.environ.get("MIN_CHARS", "3000"))
OUT = Path("affiliate-research-engine/playbook/workspace/publish")

TARGET_IDS = [
    int(x) for x in os.environ.get("TARGET_IDS", "").replace(" ", "").split(",") if x
]

SKIP_MARKS = ("【Threads用】", "【メモ】", "【社内")
UNCATEGORIZED_ID = 1


def get_post(post_id):
    r = requests.get(
        f"{WP_BASE}/posts/{post_id}",
        auth=(WP_USER, WP_PASS),
        params={"_fields": "id,title,status,content,categories,featured_media,link"},
        headers={"User-Agent": "Mozilla/5.0"},
        verify=False,
        timeout=30,
    )
    return r.json() if r.status_code == 200 else None


def publish(post_id):
    r = requests.post(
        f"{WP_BASE}/posts/{post_id}",
        auth=(WP_USER, WP_PASS),
        json={"status": "publish"},
        headers={"User-Agent": "Mozilla/5.0"},
        verify=False,
        timeout=30,
    )
    return (r.status_code in (200, 201)), r


def preflight(post):
    """公開してよいか確かめる。問題があれば理由を返す。"""
    issues = []
    title = post["title"]["rendered"]
    body = post.get("content", {}).get("rendered", "")
    text = re.sub(r"<[^>]+>", "", body)

    if any(m in title for m in SKIP_MARKS):
        issues.append("内部メモなので記事ではない")

    if not post.get("featured_media"):
        issues.append("アイキャッチ画像が未設定")

    cats = post.get("categories") or []
    if not cats or cats == [UNCATEGORIZED_ID]:
        issues.append("カテゴリが未分類")

    if len(text) < MIN_CHARS:
        issues.append(f"本文が{len(text)}字（下限{MIN_CHARS}字）")

    if "af.moshimo.com" not in body and "px.a8.net" not in body:
        issues.append("CTAボックスが入っていない")

    # 台帳の裏付けが無い、さくら固有の事実。**自動で薄めずに公開を止める**
    for b in _q.generation_blockers(body)[:8]:
        issues.append(b)

    return issues


def main():
    if not TARGET_IDS:
        print("TARGET_IDS が空。対象を指定してください。")
        sys.exit(1)

    OUT.mkdir(parents=True, exist_ok=True)
    print(f"{'DRY RUN' if DRY_RUN else 'LIVE'} — 対象 {len(TARGET_IDS)}件\n")
    report = [f"# Publish Report\nMode: {'DRY RUN' if DRY_RUN else 'LIVE'}\n\n"]
    done = skipped = failed = 0

    for pid in TARGET_IDS:
        post = get_post(pid)
        if not post:
            print(f"[{pid}] ✗ 取得失敗")
            report.append(f"- [{pid}] FETCH FAILED\n")
            failed += 1
            continue

        title = post["title"]["rendered"]

        if post.get("status") == "publish":
            print(f"[{pid}] − すでに公開済み")
            report.append(f"- [{pid}] {title[:40]} — すでに公開済み\n")
            skipped += 1
            continue

        issues = preflight(post)
        if issues:
            print(f"[{pid}] ✗ 公開しない: {' / '.join(issues)}")
            print(f"       {title[:50]}")
            report.append(f"- [{pid}] {title[:40]} — **公開見送り**: {' / '.join(issues)}\n")
            skipped += 1
            continue

        print(f"[{pid}] {title[:46]}")
        if DRY_RUN:
            report.append(f"- [{pid}] {title[:40]} — 公開可（DRY RUN）\n")
            done += 1
            continue

        ok, r = publish(pid)
        if ok:
            link = r.json().get("link", "")
            print(f"   ✓ 公開 {link}")
            report.append(f"- [{pid}] {title[:40]} — **公開** {link}\n")
            done += 1
        else:
            print(f"   ✗ 失敗 HTTP {r.status_code}")
            report.append(f"- [{pid}] {title[:40]} — FAILED HTTP {r.status_code}\n")
            failed += 1
        time.sleep(2)

    summary = f"\n## 集計\n- 公開: {done}件\n- 見送り: {skipped}件\n- 失敗: {failed}件\n"
    print(summary)
    report.append(summary)
    (OUT / "PUBLISH_REPORT.md").write_text("".join(report), encoding="utf-8")


if __name__ == "__main__":
    main()
