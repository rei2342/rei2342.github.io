#!/usr/bin/env python3
"""
cta_restore.py
一時非表示にしたCTAを、正しいリンクへ差し替えて再表示する。

やること:
  1. 旧リンクの使用箇所を全記事から洗い出す（今回の対象以外も見る）
  2. <!-- cta-hidden --> の包みを外す
  3. 旧URLを新URLへ差し替える
  4. アンカー文言を、公式で確認できた範囲の中立表現にする
  5. 差し替え後の遷移先を1回だけたどって記録する

  DRY_RUN=false python cta_restore.py
出力: workspace/backups/<日付>/CTA_RESTORE.md
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
import quality_rules as _q
import wp_audit as _wa

JST = timezone(timedelta(hours=9))
WP_BASE = "https://sakura-eigo.com/wp-json/wp/v2"
WP_USER = "rei.00pt2342@gmail.com"
WP_PASS = os.environ.get("WP_APP_PASSWORD", "")
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"
BK = Path("affiliate-research-engine/playbook/workspace/backups")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0"}

# (旧リンクの目印, 新URL, 新しいアンカー文言, 案件名)
SWAPS = [
    ("4B9W9D+2IHWQA+4HHM+669JM",
     "https://px.a8.net/svt/ejp?a8mat=4B9W9D+2IHWQA+4HHM+60H7M",
     "→ QQ English公式サイトでレッスンの内容と料金を確認する",
     "QQ English"),
]

# URLは変えず、**文言だけ**を中立にするもの。
# 未確認の訴求（speekの「無料トライアル」など）を全記事から外す
ANCHOR_ONLY = [
    ("a_id=5640991", "speek",
     "→ speek公式サイトで発音矯正スクールの内容を確認する"),
]

HIDDEN = re.compile(r"<!--\s*cta-hidden:START[^>]*?-->(.*?)<!--\s*cta-hidden:END\s*-->",
                    re.DOTALL | re.IGNORECASE)


def main():
    day = datetime.now(JST).strftime("%Y-%m-%d")
    (BK / day).mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    L = [f"# CTAの差し替え {stamp}\n\n",
         f"モード: **{'DRY RUN（書いていない）' if DRY_RUN else 'LIVE（書いた）'}**\n\n"]

    posts = _wa.published()
    print(f"{'DRY RUN' if DRY_RUN else 'LIVE'} — 公開 {len(posts)}本を走査\n")

    for old, new, anchor, svc in SWAPS:
        hits = [p for p in posts if old in p.get("content", {}).get("rendered", "")]
        L.append(f"\n---\n\n## {svc}\n\n")
        L.append(f"- **旧**: `{old}`（使わない）\n- **新**: `{new}`\n")
        L.append(f"- **新しい文言**: {anchor}\n")
        L.append(f"- **旧リンクを含む公開記事**: {len(hits)}本 "
                 f"（{' '.join(str(p['id']) for p in hits)}）\n\n")
        print(f"{svc}: 旧リンクを含む記事 {len(hits)}本")

        # 遷移先を1回だけ確かめる
        try:
            r = requests.get(new, headers=UA, timeout=45, verify=False,
                             allow_redirects=True)
            t = re.search(r"<title[^>]*>(.*?)</title>", r.text, re.DOTALL | re.I)
            title = _q.strip_tags(t.group(1)).strip() if t else ""
            L.append(f"### 差し替え先の確認（{stamp}）\n\n"
                     f"- HTTP: {r.status_code}\n- 最終URL: {r.url}\n"
                     f"- ページタイトル: {title}\n"
                     f"- 判定: "
                     f"{'✅ 子ども向けではない' if 'qqkids' not in r.url and 'キッズ' not in title else '❌ まだ子ども向け'}\n\n")
            print(f"   → {r.url}\n   → {title}")
        except Exception as e:
            L.append(f"- 遷移先を確認できなかった: {e}\n\n")

        for p in hits:
            pid = p["id"]
            res = requests.get(f"{WP_BASE}/posts/{pid}", auth=(WP_USER, WP_PASS),
                               params={"context": "edit"}, headers=UA,
                               verify=False, timeout=40)
            if res.status_code != 200:
                print(f"[{pid}] ✗ 取得できない")
                continue
            raw = res.json()["content"]["raw"]
            (BK / day / f"{pid}_ctarestore.json").write_text(json.dumps(
                {"id": pid, "content_raw": raw,
                 "modified": res.json().get("modified")},
                ensure_ascii=False, indent=2), encoding="utf-8")

            body = HIDDEN.sub(lambda m: m.group(1), raw)   # 包みを外す
            body = body.replace(old, new.split("a8mat=")[1])
            # アンカー文言を差し替える
            body = re.sub(
                r'(<a[^>]+a8mat=' + re.escape(new.split("a8mat=")[1]) +
                r'[^>]*>)(.*?)(</a>)',
                lambda m: m.group(1) + anchor + m.group(3),
                body, flags=re.DOTALL)

            n_old = raw.count(old)
            n_new = body.count(new.split("a8mat=")[1])
            print(f"[{pid}] 旧{n_old}箇所 → 新{n_new}箇所"
                  + ("（DRY RUN）" if DRY_RUN else ""))
            L.append(f"- 記事 {pid}: 旧 {n_old}箇所 → 新 {n_new}箇所")

            if not DRY_RUN:
                up = requests.post(f"{WP_BASE}/posts/{pid}",
                                   auth=(WP_USER, WP_PASS), headers=UA,
                                   verify=False, timeout=60,
                                   json={"content": body})
                L.append(f" … {'✅ 反映' if up.status_code in (200, 201) else '❌ ' + str(up.status_code)}\n")
            else:
                L.append(" … （DRY RUN）\n")

    # ── 文言だけの中立化（URLは触らない）──
    for needle, svc, anchor in ANCHOR_ONLY:
        hits = [p for p in posts
                if needle in p.get("content", {}).get("rendered", "")]
        L.append(f"\n---\n\n## {svc}（文言だけ中立化）\n\n")
        L.append(f"- **新しい文言**: {anchor}\n")
        L.append(f"- **対象記事**: {len(hits)}本\n\n")
        print(f"\n{svc} 文言中立化: {len(hits)}本")
        for p in hits:
            pid = p["id"]
            res = requests.get(f"{WP_BASE}/posts/{pid}", auth=(WP_USER, WP_PASS),
                               params={"context": "edit"}, headers=UA,
                               verify=False, timeout=40)
            if res.status_code != 200:
                continue
            raw = res.json()["content"]["raw"]
            (BK / day / f"{pid}_anchor.json").write_text(json.dumps(
                {"id": pid, "content_raw": raw}, ensure_ascii=False, indent=2),
                encoding="utf-8")
            body = re.sub(
                r'(<a[^>]+' + re.escape(needle) + r'[^>]*>)(.*?)(</a>)',
                lambda m: m.group(1) + anchor + m.group(3),
                raw, flags=re.DOTALL)
            n = len(re.findall(re.escape(anchor), body))
            print(f"[{pid}] {n}箇所" + ("（DRY RUN）" if DRY_RUN else ""))
            L.append(f"- 記事 {pid}: {n}箇所")
            if DRY_RUN or body == raw:
                L.append(" …（変更なし）\n")
                continue
            up = requests.post(f"{WP_BASE}/posts/{pid}", auth=(WP_USER, WP_PASS),
                               headers=UA, verify=False, timeout=60,
                               json={"content": body})
            L.append(f" … {'✅' if up.status_code in (200, 201) else '❌ ' + str(up.status_code)}\n")

    (BK / day / "CTA_RESTORE.md").write_text("".join(L), encoding="utf-8")
    print(f"\n→ workspace/backups/{day}/CTA_RESTORE.md")


if __name__ == "__main__":
    main()
