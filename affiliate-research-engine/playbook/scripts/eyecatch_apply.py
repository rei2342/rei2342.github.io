#!/usr/bin/env python3
"""
eyecatch_apply.py
コンタクトシートの承認後に、**1回だけ**走らせる。ここが唯一サイトを触る場所。

  python eyecatch_apply.py            … 何をするかを並べるだけ（サイトは触らない）
  python eyecatch_apply.py --approve  … 実行する

順番は固定。途中で判断を求めない。

  1. バックアップ（現在の featured_media・画像URL・予約日時）
  2. メディアへアップロード（半角英数のファイル名・alt を設定）
  3. featured_media を差し替え
  4. 公開済み993の画像を差し替え
  5. 予約5本を、**元の予約日時のまま** future へ戻す
  6. 公開画面・OGP・alt・メディア対応を確認
  7. ロールバック手順を backups/ へ書く

**検査に落ちた画像がある記事は、その記事だけ飛ばす。** 仮画像を当てない。
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import urllib3
import yaml

urllib3.disable_warnings()

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
import eyecatch_spec as es

JST = timezone(timedelta(hours=9))
WP_BASE = "https://sakura-eigo.com/wp-json/wp/v2"
WP_USER = "rei.00pt2342@gmail.com"
WP_PASS = os.environ.get("WP_APP_PASSWORD", "")
AUTH = (WP_USER, WP_PASS)
UA = {"User-Agent": "Mozilla/5.0"}

BATCH = ROOT / "eyecatch-generation-batch/ai-6"
OUT = BATCH / "out"
ARTICLES = ROOT / "config/eyecatch/articles-ai-cluster.yaml"
STAMP = datetime.now(JST).strftime("%Y-%m-%d")
BK = ROOT / f"workspace/backups/{STAMP}/eyecatch-ai6"
# 予約を止めたときの記録。**元の日時はここにしか残っていない**
PAUSE = ROOT / "workspace/backups/2026-08-09"


def get(path, **params):
    r = requests.get(f"{WP_BASE}/{path}", auth=AUTH, params=params,
                     headers=UA, verify=False, timeout=40)
    return r.json() if r.status_code == 200 else None


def post(path, payload):
    r = requests.post(f"{WP_BASE}/{path}", auth=AUTH, json=payload,
                      headers=UA, verify=False, timeout=60)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"{path} {r.status_code} {r.text[:200]}")
    return r.json()


def failed_ids():
    """CHECKS.md で落ちた記事。**落ちた記事は反映しない。**"""
    f = BATCH / "CHECKS.md"
    if not f.exists():
        return None
    tail = f.read_text(encoding="utf-8").split("## 再生成が必要なもの")[-1]
    return {int(m) for m in re.findall(r"^\|\s*(\d+)\s*\|", tail, re.M)}


def plan_rows(doc):
    rows = []
    for a in doc["articles"]:
        pid = a["post_id"]
        rows.append({
            "post_id": pid,
            "blog": OUT / a["filename"],
            "note": OUT / a["filename"].replace(".jpg", "-note.jpg"),
            "alt": a["alt"],
            "filename": a["filename"],
        })
    return rows


def upload(path, alt):
    with open(path, "rb") as fh:
        r = requests.post(
            f"{WP_BASE}/media", auth=AUTH, data=fh.read(),
            headers={**UA, "Content-Type": "image/jpeg",
                     "Content-Disposition":
                         f'attachment; filename="{path.name}"'},
            verify=False, timeout=120)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"media {r.status_code} {r.text[:200]}")
    m = r.json()
    post(f"media/{m['id']}", {"alt_text": alt})
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--approve", action="store_true",
                    help="実際にWordPressへ反映する")
    args = ap.parse_args()

    doc = es.load_articles(ARTICLES)
    rows = plan_rows(doc)

    missing = [str(r["post_id"]) for r in rows if not r["blog"].exists()]
    if missing:
        print("完成版が無い: " + " ".join(missing))
        print("先に eyecatch_finish.py を通す。**仮画像は当てない。**")
        sys.exit(1)

    ng = failed_ids()
    if ng is None:
        print("CHECKS.md が無い。先に eyecatch_finish.py を通す。")
        sys.exit(1)
    if ng:
        print("検査に落ちている: " + " ".join(map(str, sorted(ng)))
              + " … この記事は飛ばす")
    rows = [r for r in rows if r["post_id"] not in ng]

    # 予約を止めたときの元日時
    resume = {}
    for f in PAUSE.glob("ai_pause_*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        resume[int(d["id"])] = d

    print(f"\n対象 {len(rows)}本 / 予約を戻す {len(resume)}本")
    for r in rows:
        pid = r["post_id"]
        back = resume.get(pid)
        when = f"予約 {back['date']} へ戻す" if back else "公開中のまま差し替え"
        print(f"  {pid}  {r['filename']}  {when}")

    if not args.approve:
        print("\n--approve が無いので、ここで終わり。**サイトは触っていない。**")
        return

    if not WP_PASS:
        print("WP_APP_PASSWORD が無い。")
        sys.exit(1)

    BK.mkdir(parents=True, exist_ok=True)
    log = []
    for r in rows:
        pid = r["post_id"]
        # 1. バックアップ
        cur = get(f"posts/{pid}", context="edit",
                  _fields="id,status,date,featured_media,slug")
        old_url = None
        if cur and cur.get("featured_media"):
            m = get(f"media/{cur['featured_media']}", _fields="id,source_url")
            old_url = (m or {}).get("source_url")
        (BK / f"{pid}.json").write_text(json.dumps({
            "id": pid, "checked_at": STAMP,
            "old_featured_media": (cur or {}).get("featured_media"),
            "old_source_url": old_url,
            "old_status": (cur or {}).get("status"),
            "old_date": (cur or {}).get("date"),
        }, ensure_ascii=False, indent=2), encoding="utf-8")

        # 2-3. アップロードして差し替え
        media = upload(r["blog"], r["alt"])
        payload = {"featured_media": media["id"]}
        # 5. 予約は元の日時のまま future へ戻す
        back = resume.get(pid)
        if back and back.get("status") == "future":
            payload.update({"status": "future", "date": back["date"]})
        post(f"posts/{pid}", payload)
        log.append({"post_id": pid, "new_media": media["id"],
                    "url": media["source_url"],
                    "restored_to": payload.get("date")})
        print(f"[{pid}] media {media['id']} ← {r['filename']}"
              + (f" / 予約 {payload['date']}" if "date" in payload else ""))

    # 6. 反映後の確認
    checks = []
    for e in log:
        p = get(f"posts/{e['post_id']}",
                _fields="id,status,date,link,featured_media")
        m = get(f"media/{e['new_media']}", _fields="id,source_url,alt_text")
        url = (m or {}).get("source_url", "")
        ok_name = bool(re.fullmatch(r"[a-z0-9\-]+\.jpg", url.split("/")[-1]))
        # OGP。公開中の記事だけ、実際のHTMLを取って og:image を照合する。
        # ファイル名が半角英数でないと Meta のクローラーが取りに行けない
        og = None
        if (p or {}).get("status") == "publish" and p.get("link"):
            h = requests.get(p["link"], headers=UA, verify=False, timeout=40)
            hit = re.search(r'property="og:image"[^>]*content="([^"]+)"',
                            h.text)
            og = hit.group(1) if hit else None
        checks.append({
            "post_id": e["post_id"],
            "featured_media_set": (p or {}).get("featured_media") == e["new_media"],
            "alt_set": bool((m or {}).get("alt_text")),
            "filename_ascii": ok_name,
            "og_image": og,
            "og_matches": (og is None) or (og.split("/")[-1] == url.split("/")[-1]),
            "status": (p or {}).get("status"),
            "date": (p or {}).get("date"),
            "link": (p or {}).get("link"),
        })

    # 7. ロールバック手順
    (BK / "APPLIED.yaml").write_text(yaml.safe_dump({
        "applied_at": datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST"),
        "items": log,
        "verify": checks,
        "rollback": (
            f"workspace/backups/{STAMP}/eyecatch-ai6/<記事ID>.json の "
            "old_featured_media と old_status・old_date を戻す。"
            "古いメディアは消していないので、IDを指すだけで戻る"),
    }, allow_unicode=True, sort_keys=False), encoding="utf-8")
    bad = [c for c in checks
           if not (c["featured_media_set"] and c["alt_set"]
                   and c["filename_ascii"] and c["og_matches"])]
    print(f"\n→ {BK}/APPLIED.yaml")
    print("確認に落ちた記事: " + (" ".join(str(c["post_id"]) for c in bad)
                                 if bad else "なし"))


if __name__ == "__main__":
    main()
