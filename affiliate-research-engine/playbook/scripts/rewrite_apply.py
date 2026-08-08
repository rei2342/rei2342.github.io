#!/usr/bin/env python3
"""
rewrite_apply.py
安全性改修した本文を WordPress へ反映する。**戻せる形でしか書かない。**

反映してよい条件（1つでも欠けたら書かない）:
  - draft_gate を通っている（未確認の一人称事実 0 / 公式情報に出典と確認日）
  - cta_claim_gate を通っている（CTAの訴求が案件台帳と一致）
  - 反映前のタイトル・本文・CTA・更新日時をバックアップ済み

変えるもの: タイトル / 本文 / 見出し / CTA文言 / CTAの表示・非表示
変えないもの: slug / URL / 公開ステータス / 元の公開日 / 記事ID

  DRY_RUN=false POSTS=310,304 python rewrite_apply.py
出力:
  workspace/backups/<日付>/<id>.json   … 戻すための完全な控え
  workspace/backups/<日付>/APPLY.md    … 何を書いたかの記録
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

JST = timezone(timedelta(hours=9))
WP_BASE = "https://sakura-eigo.com/wp-json/wp/v2"
WP_USER = "rei.00pt2342@gmail.com"
WP_PASS = os.environ.get("WP_APP_PASSWORD", "")
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"
POSTS = [x.strip() for x in os.environ.get("POSTS", "").split(",") if x.strip()]

SRC = Path("affiliate-research-engine/playbook/workspace/claims/rewrites")
TITLES = Path("affiliate-research-engine/playbook/workspace/claims/rewrites/TITLES.json")
BK = Path("affiliate-research-engine/playbook/workspace/backups")

H = {"User-Agent": "Mozilla/5.0"}


def get(pid):
    r = requests.get(f"{WP_BASE}/posts/{pid}", auth=(WP_USER, WP_PASS),
                     params={"context": "edit"}, headers=H, verify=False,
                     timeout=40)
    return r.json() if r.status_code == 200 else None


def backup(post, day):
    d = BK / day
    d.mkdir(parents=True, exist_ok=True)
    keep = {k: post.get(k) for k in
            ("id", "date", "date_gmt", "modified", "modified_gmt", "slug",
             "status", "link", "type", "featured_media", "categories", "tags")}
    keep["title_raw"] = (post.get("title") or {}).get("raw", "")
    keep["content_raw"] = (post.get("content") or {}).get("raw", "")
    keep["excerpt_raw"] = (post.get("excerpt") or {}).get("raw", "")
    keep["cta_links"] = re.findall(
        r'<a[^>]+href="([^"]*(?:af\.moshimo\.com|px\.a8\.net)[^"]*)"',
        keep["content_raw"])
    (d / f"{post['id']}.json").write_text(
        json.dumps(keep, ensure_ascii=False, indent=2), encoding="utf-8")
    return keep


def main():
    stamp = datetime.now(JST)
    day = stamp.strftime("%Y-%m-%d")
    ids = POSTS or [f.stem for f in SRC.glob("*.html")]
    titles = json.loads(TITLES.read_text(encoding="utf-8")) if TITLES.exists() else {}

    print(f"{'DRY RUN' if DRY_RUN else 'LIVE'} — {len(ids)}件\n")
    L = [f"# 反映の記録 {stamp.strftime('%Y-%m-%d %H:%M:%S JST')}\n\n",
         f"モード: **{'DRY RUN（書いていない）' if DRY_RUN else 'LIVE（書いた）'}**\n\n",
         "変えたもの: タイトル / 本文 / 見出し / CTA文言\n"
         "変えていないもの: slug / URL / 公開ステータス / 公開日 / 記事ID\n\n"]
    ok = ng = 0

    for pid in ids:
        f = SRC / f"{pid}.html"
        if not f.exists():
            print(f"[{pid}] ✗ 改修版が無い")
            continue
        body = f.read_text(encoding="utf-8")

        # ゲート。通らないものは絶対に書かない
        blockers = _q.generation_blockers(body)
        if blockers:
            print(f"[{pid}] ✗ ゲート不合格 {len(blockers)}件。書かない")
            for b in blockers[:5]:
                print(f"      {b[:110]}")
            L.append(f"\n## ❌ {pid} … ゲート不合格で書いていない\n\n"
                     + "".join(f"- {b}\n" for b in blockers))
            ng += 1
            continue

        post = get(pid)
        if not post:
            print(f"[{pid}] ✗ 取得できない")
            ng += 1
            continue

        old = backup(post, day)
        new_title = titles.get(str(pid), old["title_raw"])

        L.append(f"\n---\n\n## 記事 {pid}\n\n")
        L.append(f"- **バックアップ**: `workspace/backups/{day}/{pid}.json`\n")
        L.append(f"- **slug**: `{old['slug']}`（変更しない）\n")
        L.append(f"- **公開ステータス**: `{old['status']}`（変更しない）\n")
        L.append(f"- **公開日**: {old['date']}（変更しない）\n")
        L.append(f"- **更新日時（反映前）**: {old['modified']}\n")
        L.append(f"- **タイトル**\n  - 前: {old['title_raw']}\n  - 後: {new_title}\n")
        L.append(f"- **本文**: {len(_q.strip_tags(old['content_raw']))}字 → "
                 f"{len(_q.strip_tags(body))}字\n")
        L.append(f"- **CTAリンク**: {len(old['cta_links'])}本 → "
                 f"{len(re.findall(r'af.moshimo.com|px.a8.net', body))}本\n")

        if DRY_RUN:
            print(f"[{pid}] DRY RUN（バックアップのみ）")
            ok += 1
            continue

        r = requests.post(f"{WP_BASE}/posts/{pid}", auth=(WP_USER, WP_PASS),
                          headers=H, verify=False, timeout=60,
                          json={"title": new_title, "content": body})
        if r.status_code in (200, 201):
            print(f"[{pid}] ✓ 反映")
            L.append("- **結果**: ✅ 反映した\n")
            ok += 1
        else:
            print(f"[{pid}] ✗ {r.status_code} {r.text[:150]}")
            L.append(f"- **結果**: ❌ {r.status_code}\n")
            ng += 1

    (BK / day).mkdir(parents=True, exist_ok=True)
    (BK / day / "APPLY.md").write_text("".join(L), encoding="utf-8")
    print(f"\n成功 {ok} / 失敗 {ng}")
    print(f"バックアップ: workspace/backups/{day}/")
    return 1 if ng else 0


if __name__ == "__main__":
    sys.exit(main())
