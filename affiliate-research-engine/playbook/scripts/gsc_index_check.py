#!/usr/bin/env python3
"""
gsc_index_check.py
公開記事が Google にインデックスされているかを1本ずつ調べる。

検索パフォーマンスが0のとき、
「まだデータが入っていない」のか「そもそも登録されていない」のかを
切り分けないと次の手が決まらない。URL検査APIで実際の状態を見る。
"""
import json
import os
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

import requests
import urllib3
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleRequest

urllib3.disable_warnings()

SITE = "sc-domain:sakura-eigo.com"
INSPECT = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

WP_BASE = "https://sakura-eigo.com/wp-json/wp/v2"
WP_USER = "rei.00pt2342@gmail.com"
WP_PASS = os.environ.get("WP_APP_PASSWORD", "")
LIMIT = int(os.environ.get("LIMIT", "50"))
OUT = Path("affiliate-research-engine/playbook/workspace/gsc")


def token():
    raw = os.environ.get("GSC_SERVICE_ACCOUNT_JSON", "")
    if not raw:
        print("GSC_SERVICE_ACCOUNT_JSON が未設定")
        sys.exit(1)
    creds = service_account.Credentials.from_service_account_info(
        json.loads(raw), scopes=SCOPES)
    creds.refresh(GoogleRequest())
    return creds.token


def published():
    posts, page = [], 1
    while True:
        r = requests.get(f"{WP_BASE}/posts", auth=(WP_USER, WP_PASS),
                         params={"per_page": 100, "page": page, "status": "publish",
                                 "_fields": "id,link,title,date"},
                         headers={"User-Agent": "Mozilla/5.0"},
                         verify=False, timeout=40)
        if r.status_code != 200:
            break
        b = r.json()
        if not b:
            break
        posts += b
        if len(b) < 100:
            break
        page += 1
    return posts


def inspect(tok, url):
    r = requests.post(INSPECT,
                      headers={"Authorization": f"Bearer {tok}"},
                      json={"inspectionUrl": url, "siteUrl": SITE,
                            "languageCode": "ja"},
                      timeout=60)
    if r.status_code != 200:
        return {"error": f"HTTP {r.status_code} {r.text[:120]}"}
    return r.json().get("inspectionResult", {}).get("indexStatusResult", {})


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    tok = token()
    posts = published()[:LIMIT]
    print(f"公開記事 {len(posts)}件を検査\n")

    rows, verdicts = [], Counter()
    for i, p in enumerate(posts, 1):
        res = inspect(tok, p["link"])
        verdict = res.get("coverageState") or res.get("error") or "不明"
        crawl = (res.get("lastCrawlTime") or "")[:10] or "未クロール"
        verdicts[verdict] += 1
        title = p["title"]["rendered"][:34]
        print(f"{i:>3}/{len(posts)} [{p['id']:>4}] {crawl:<12} {verdict[:40]}  {title}")
        rows.append((p["id"], title, crawl, verdict))
        time.sleep(1.2)      # APIを叩きすぎない

    stamp = date.today().isoformat()
    L = [f"# インデックス状況 {stamp}\n\n",
         f"公開記事 {len(posts)}件を URL検査API で確認\n\n",
         "## 集計\n\n| 状態 | 件数 |\n|---|---|\n"]
    for v, n in verdicts.most_common():
        L.append(f"| {v} | {n} |\n")
    L.append("\n## 記事別\n\n| ID | 最終クロール | 状態 | タイトル |\n|---|---|---|---|\n")
    for pid, title, crawl, verdict in rows:
        L.append(f"| {pid} | {crawl} | {verdict} | {title} |\n")

    (OUT / f"{stamp}_INDEX.md").write_text("".join(L), encoding="utf-8")
    (OUT / "INDEX_LATEST.md").write_text("".join(L), encoding="utf-8")
    print("\n=== 集計 ===")
    for v, n in verdicts.most_common():
        print(f"  {n:>3}件  {v}")


if __name__ == "__main__":
    main()
