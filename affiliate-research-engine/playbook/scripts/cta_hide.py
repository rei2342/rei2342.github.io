#!/usr/bin/env python3
"""
cta_hide.py
CTA_ACTIONS.csv で hide_temporarily にした案件のCTAを、記事から一時的に隠す。

**リンクを削除しない。** HTMLコメントで包んで表示だけ止める。
差し替え用のリンクがそのまま残るので、あとで戻せる。

  DRY_RUN=false python cta_hide.py
出力: workspace/backups/<日付>/<id>_cta.json
"""
import csv
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

JST = timezone(timedelta(hours=9))
WP_BASE = "https://sakura-eigo.com/wp-json/wp/v2"
WP_USER = "rei.00pt2342@gmail.com"
WP_PASS = os.environ.get("WP_APP_PASSWORD", "")
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"

ACTIONS = Path("affiliate-research-engine/playbook/workspace/claims/CTA_ACTIONS.csv")
BK = Path("affiliate-research-engine/playbook/workspace/backups")
H = {"User-Agent": "Mozilla/5.0"}

MARK_A = "<!-- cta-hidden:START "
MARK_B = " -->"
MARK_END = "<!-- cta-hidden:END -->"


def hide_blocks(html, needle):
    """その案件のCTAを含む段落を、コメントで包んで表示だけ止める。"""
    out, n = html, 0

    def repl(m):
        nonlocal n
        block = m.group(0)
        if needle not in block or MARK_A in block:
            return block
        n += 1
        return f"{MARK_A}{needle}{MARK_B}{block}{MARK_END}"

    out = re.sub(r"<p\b[^>]*>.*?</p>", repl, out, flags=re.DOTALL | re.I)
    return out, n


def main():
    if not ACTIONS.exists():
        print("CTA_ACTIONS.csv が無い")
        return 0
    todo = [r for r in csv.DictReader(ACTIONS.open(encoding="utf-8"))
            if r["action"] == "hide_temporarily" and r["status"] == "pending"]
    if not todo:
        print("一時非表示にする対象は無い")
        return 0

    day = datetime.now(JST).strftime("%Y-%m-%d")
    (BK / day).mkdir(parents=True, exist_ok=True)
    print(f"{'DRY RUN' if DRY_RUN else 'LIVE'} — {len(todo)}件の対応\n")

    for r in todo:
        # リンクの一部で照合する。クエリのエスケープ差を避けるため a8mat だけ見る
        m = re.search(r"a8mat=([^&\s]+)", r["current_url"]) or \
            re.search(r"a_id=([0-9]+)", r["current_url"])
        needle = m.group(1) if m else r["current_url"][:40]
        for pid in r["post_ids"].split():
            res = requests.get(f"{WP_BASE}/posts/{pid}", auth=(WP_USER, WP_PASS),
                               params={"context": "edit"}, headers=H,
                               verify=False, timeout=40)
            if res.status_code != 200:
                print(f"[{pid}] ✗ 取得できない {res.status_code}")
                continue
            post = res.json()
            raw = post["content"]["raw"]
            new, n = hide_blocks(raw, needle)
            (BK / day / f"{pid}_cta.json").write_text(json.dumps(
                {"id": pid, "service": r["service"], "needle": needle,
                 "content_raw": raw, "modified": post.get("modified")},
                ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[{pid}] {r['service']} … {n}箇所を非表示" +
                  ("（DRY RUN）" if DRY_RUN else ""))
            if DRY_RUN or n == 0:
                continue
            up = requests.post(f"{WP_BASE}/posts/{pid}", auth=(WP_USER, WP_PASS),
                               headers=H, verify=False, timeout=60,
                               json={"content": new})
            print(f"      → {'✓ 反映' if up.status_code in (200, 201) else '✗ ' + str(up.status_code)}")
    print(f"\nバックアップ: workspace/backups/{day}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
