#!/usr/bin/env python3
"""
hold_release.py
一次情報の照合に落ちて下書きで止めた記事を、照合し直して出す。

AI記事の #5（発音矯正）は speek.jp が ConnectTimeout で落ちた。
既存の公開記事10本が同じURLを引用していて、そちらは通っているので、
**一時的に取れなかっただけ**の可能性が高い。ただし推測では出さない。
取り直して200が返り、語が載っていることを確かめてから予約に切り替える。

  POST=999 URL=https://speek.jp/ WORDS=speek WHEN=2026-08-12T07:00:00 \
  DRY_RUN=false python hold_release.py
出力: workspace/backups/<日付>/HOLD_RELEASE.md
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings()
sys.path.insert(0, str(Path(__file__).parent))
import quality_rules as _q

JST = timezone(timedelta(hours=9))
WP = "https://sakura-eigo.com/wp-json/wp/v2"
AUTH = ("rei.00pt2342@gmail.com", os.environ.get("WP_APP_PASSWORD", ""))
UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) "
                     "Chrome/124.0 Safari/537.36")}
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"
BK = Path("affiliate-research-engine/playbook/workspace/backups")

POST = os.environ.get("POST", "")
URL = os.environ.get("URL", "")
WORDS = [w for w in os.environ.get("WORDS", "").split(",") if w]
WHEN = os.environ.get("WHEN", "")
TRIES = int(os.environ.get("TRIES", "3"))


def main():
    day = datetime.now(JST).strftime("%Y-%m-%d")
    (BK / day).mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    L = [f"# 保留した記事の再照合 {stamp}\n\n",
         f"モード: **{'DRY RUN' if DRY_RUN else 'LIVE'}**\n\n",
         f"記事 {POST} / 引用元 {URL} / 探す語 {' '.join(WORDS)}\n\n",
         "| 回 | 結果 |\n|---|---|\n"]

    ok, note = False, ""
    for i in range(1, TRIES + 1):
        try:
            r = requests.get(URL, headers=UA, timeout=60, verify=False,
                             allow_redirects=True)
            if r.status_code != 200:
                note = f"HTTP {r.status_code}"
            else:
                text = _q.strip_tags(r.text)
                hit = [w for w in WORDS if w.lower() in text.lower()]
                if hit:
                    ok, note = True, f"HTTP 200・「{hit[0]}」を確認"
                else:
                    note = f"語が見つからない: {' / '.join(WORDS)}"
        except Exception as e:
            note = f"取得できず {type(e).__name__}"
        L.append(f"| {i} | {'✅' if ok else '❌'} {note} |\n")
        print(f"[{i}] {note}")
        if ok:
            break

    if not ok:
        L.append("\n**3回とも落ちたので、下書きのまま残す。**\n"
                 "引用元が開けない状態で公開すると、確認できていない主張を出すことになる。\n")
        (BK / day / "HOLD_RELEASE.md").write_text("".join(L), encoding="utf-8")
        print("下書きのまま残す")
        return

    if DRY_RUN:
        L.append(f"\n（DRY RUN。{WHEN} の予約に切り替えていない）\n")
    else:
        payload = {"status": "future", "date": WHEN} if WHEN else \
            {"status": "publish"}
        up = requests.post(f"{WP}/posts/{POST}", auth=AUTH, headers=UA,
                           verify=False, timeout=60, json=payload)
        good = up.status_code in (200, 201)
        L.append(f"\n**{'✅ 予約に切り替えた' if good else '❌ ' + str(up.status_code)}**"
                 f" {WHEN}\n")
        print(f"{'OK' if good else up.status_code}")
    (BK / day / "HOLD_RELEASE.md").write_text("".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
