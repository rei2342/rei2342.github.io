#!/usr/bin/env python3
"""
gsc_fetch.py
Search Console のデータを取得し、記事別・案件別に集計する。

ASPの管理画面は案件別の内訳しか出ないが、どの記事にどの案件が
入っているかはこちらで把握している。記事別のアクセスと突き合わせれば、
「どの案件を置いた記事が読まれているか」が分かる。

必要なもの:
  GSC_SERVICE_ACCOUNT_JSON … サービスアカウントの鍵（JSON文字列）
  そのサービスアカウントを Search Console のユーザーに追加しておくこと
"""
import csv
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import requests
import urllib3
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleRequest

urllib3.disable_warnings()
sys.path.insert(0, str(Path(__file__).parent))
import affiliate_inserter as _ai

SITE = "sc-domain:sakura-eigo.com"
API = "https://searchconsole.googleapis.com/webmasters/v3/sites"
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

WP_BASE = "https://sakura-eigo.com/wp-json/wp/v2"
WP_USER = "rei.00pt2342@gmail.com"
WP_PASS = os.environ.get("WP_APP_PASSWORD", "")

OUT = Path("affiliate-research-engine/playbook/workspace/gsc")
DAYS = int(os.environ.get("DAYS", "28"))


def token():
    raw = os.environ.get("GSC_SERVICE_ACCOUNT_JSON", "")
    if not raw:
        print("GSC_SERVICE_ACCOUNT_JSON が未設定")
        sys.exit(1)
    creds = service_account.Credentials.from_service_account_info(
        json.loads(raw), scopes=SCOPES)
    creds.refresh(GoogleRequest())
    return creds.token


def query(tok, dimension, rows=1000):
    """Search Console から指定ディメンションの集計を取る。"""
    end = date.today() - timedelta(days=2)      # 直近2日は未確定なので除く
    start = end - timedelta(days=DAYS)
    r = requests.post(
        f"{API}/{requests.utils.quote(SITE, safe='')}/searchAnalytics/query",
        headers={"Authorization": f"Bearer {tok}"},
        json={
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "dimensions": [dimension],
            "rowLimit": rows,
        },
        timeout=60,
    )
    if r.status_code != 200:
        print(f"API エラー {r.status_code}: {r.text[:300]}")
        sys.exit(1)
    return r.json().get("rows", []), start, end


def wp_posts():
    """公開記事の slug / title を取り、記事ごとの案件を判定する。"""
    posts, page = [], 1
    while True:
        r = requests.get(
            f"{WP_BASE}/posts",
            auth=(WP_USER, WP_PASS),
            params={"per_page": 100, "page": page, "status": "publish",
                    "_fields": "id,slug,title,content,link"},
            headers={"User-Agent": "Mozilla/5.0"}, verify=False, timeout=40)
        if r.status_code != 200:
            break
        batch = r.json()
        if not batch:
            break
        posts += batch
        if len(batch) < 100:
            break
        page += 1

    out = {}
    for p in posts:
        title = p["title"]["rendered"]
        body = p.get("content", {}).get("rendered", "")
        topic = _ai.classify_full(title, body)
        out[p["slug"]] = {
            "id": p["id"], "title": title, "topic": topic,
            "programs": _ai.TOPIC_MAP.get(topic, []),
        }
    return out


def slug_of(url):
    m = re.search(r"sakura-eigo\.com/([^/?#]+)/?", url)
    return m.group(1) if m else ""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    tok = token()

    pages, start, end = query(tok, "page")
    queries, _, _ = query(tok, "query")
    posts = wp_posts()
    stamp = date.today().isoformat()

    # 生データをCSVで残す（後から自分で見たいとき用）
    with open(OUT / f"{stamp}_pages.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["url", "clicks", "impressions", "ctr", "position"])
        for r in pages:
            w.writerow([r["keys"][0], r["clicks"], r["impressions"],
                        round(r["ctr"], 4), round(r["position"], 1)])

    with open(OUT / f"{stamp}_queries.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["query", "clicks", "impressions", "ctr", "position"])
        for r in queries:
            w.writerow([r["keys"][0], r["clicks"], r["impressions"],
                        round(r["ctr"], 4), round(r["position"], 1)])

    # 案件別に合算する。ここがASPの管理画面では出せない数字。
    prog = defaultdict(lambda: {"clicks": 0, "imp": 0, "articles": 0})
    unknown = []
    for r in pages:
        s = slug_of(r["keys"][0])
        info = posts.get(s)
        if not info:
            unknown.append(r["keys"][0])
            continue
        for p in info["programs"]:
            prog[p]["clicks"] += r["clicks"]
            prog[p]["imp"] += r["impressions"]
            prog[p]["articles"] += 1

    tot_c = sum(r["clicks"] for r in pages)
    tot_i = sum(r["impressions"] for r in pages)

    L = [f"# Search Console レポート {stamp}\n\n",
         f"対象期間: {start} 〜 {end}（{DAYS}日間）\n\n",
         f"- 合計クリック: **{tot_c}**\n- 合計表示: **{tot_i}**\n",
         f"- 平均CTR: **{(tot_c / tot_i * 100 if tot_i else 0):.2f}%**\n\n"]

    L.append("## 案件別（その案件を載せた記事の合算）\n\n")
    L.append("| 案件 | クリック | 表示 | 記事数 |\n|---|---|---|---|\n")
    for p, v in sorted(prog.items(), key=lambda x: -x[1]["clicks"]):
        L.append(f"| {p} | {v['clicks']} | {v['imp']} | {v['articles']} |\n")

    L.append("\n## 記事別 上位20\n\n")
    L.append("| クリック | 表示 | 順位 | 記事 | 案件 |\n|---|---|---|---|---|\n")
    for r in sorted(pages, key=lambda x: -x["clicks"])[:20]:
        s = slug_of(r["keys"][0])
        info = posts.get(s, {})
        L.append(f"| {r['clicks']} | {r['impressions']} | {r['position']:.1f} | "
                 f"{info.get('title', s)[:34]} | {','.join(info.get('programs', []))} |\n")

    L.append("\n## 検索語 上位30\n\n")
    L.append("| クリック | 表示 | 順位 | 検索語 |\n|---|---|---|---|\n")
    for r in sorted(queries, key=lambda x: -x["clicks"])[:30]:
        L.append(f"| {r['clicks']} | {r['impressions']} | {r['position']:.1f} | {r['keys'][0]} |\n")

    if unknown:
        L.append(f"\n## 記事と結びつかなかったURL（{len(unknown)}件）\n\n")
        for u in unknown[:10]:
            L.append(f"- {u}\n")

    (OUT / f"{stamp}_REPORT.md").write_text("".join(L), encoding="utf-8")
    (OUT / "LATEST.md").write_text("".join(L), encoding="utf-8")
    print("".join(L)[:2500])


if __name__ == "__main__":
    main()
