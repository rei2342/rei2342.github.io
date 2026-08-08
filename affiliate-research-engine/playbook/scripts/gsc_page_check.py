#!/usr/bin/env python3
"""
gsc_page_check.py
改修する前に、その記事がいま検索でどう評価されているかを見る。

維持文0の全面改修をするなら、既存の評価を捨てることになる。
流入がほぼ無いなら捨ててよいが、別の検索意図で表示されているなら、
残すべき要素があるかもしれない。**書き換える前に見る。**

  PAGES=310,304 python gsc_page_check.py
出力: workspace/gsc/PAGE_CHECK.md
"""
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import requests
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import service_account

sys.path.insert(0, str(Path(__file__).parent))
import wp_audit as _wa

SITE = "sc-domain:sakura-eigo.com"
API = "https://searchconsole.googleapis.com/webmasters/v3/sites"
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
OUT = Path("affiliate-research-engine/playbook/workspace/gsc")
DAYS = int(os.environ.get("DAYS", "90"))
PAGES = [x.strip() for x in os.environ.get("PAGES", "").split(",") if x.strip()]


def token():
    raw = os.environ.get("GSC_SERVICE_ACCOUNT_JSON", "")
    if not raw:
        print("GSC_SERVICE_ACCOUNT_JSON が未設定")
        sys.exit(1)
    creds = service_account.Credentials.from_service_account_info(
        json.loads(raw), scopes=SCOPES)
    creds.refresh(GoogleRequest())
    return creds.token


def q(tok, dims, filters=None, rows=500):
    end = date.today() - timedelta(days=2)
    start = end - timedelta(days=DAYS)
    body = {"startDate": start.isoformat(), "endDate": end.isoformat(),
            "dimensions": dims, "rowLimit": rows}
    if filters:
        body["dimensionFilterGroups"] = [{"filters": filters}]
    r = requests.post(
        f"{API}/{requests.utils.quote(SITE, safe='')}/searchAnalytics/query",
        headers={"Authorization": f"Bearer {tok}"}, json=body, timeout=60)
    if r.status_code != 200:
        print(f"API エラー {r.status_code}: {r.text[:200]}")
        return [], start, end
    return r.json().get("rows", []), start, end


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    tok = token()
    posts = {str(p["id"]): p for p in _wa.published()}
    want = PAGES or list(posts)

    L = [f"# 改修前の検索実績 {date.today().isoformat()}\n\n",
         f"直近 **{DAYS}日**（Search Console。直近2日は未確定なので除く）\n\n",
         "維持文0の全面改修をする前に、捨てる評価があるかを見るための記録。\n\n"]

    for pid in want:
        p = posts.get(str(pid))
        if not p:
            L.append(f"\n## 記事 {pid} … 公開記事に無い\n")
            continue
        url = p.get("link", "")
        title = re.sub(r"<[^>]+>", "", p["title"]["rendered"])
        rows, start, end = q(tok, ["query"],
                             [{"dimension": "page", "operator": "equals",
                               "expression": url}])
        tot = defaultdict(float)
        for r in rows:
            tot["imp"] += r.get("impressions", 0)
            tot["clk"] += r.get("clicks", 0)
        pos = ([r for r in rows] or [{}])
        avg = (sum(r.get("position", 0) * r.get("impressions", 0) for r in rows)
               / tot["imp"]) if tot["imp"] else 0

        L.append(f"\n---\n\n## 記事 {pid}｜{title}\n\n{url}\n\n")
        L.append(f"- **表示回数 {int(tot['imp'])}** / "
                 f"**クリック {int(tot['clk'])}** / "
                 f"**平均掲載順位 {avg:.1f}** / 検索語 {len(rows)}種\n")
        if not rows:
            L.append("- **検索での表示が0件。** 捨てる評価は無い。全面改修してよい\n")
            print(f"[{pid}] 表示0 / {title[:30]}")
            continue
        print(f"[{pid}] imp={int(tot['imp'])} clk={int(tot['clk'])} "
              f"pos={avg:.1f} / {title[:30]}")
        L.append("\n| 検索語 | 表示 | クリック | 順位 |\n|---|---|---|---|\n")
        for r in sorted(rows, key=lambda x: -x.get("impressions", 0))[:20]:
            L.append(f"| {r['keys'][0]} | {int(r.get('impressions',0))} "
                     f"| {int(r.get('clicks',0))} | {r.get('position',0):.1f} |\n")

    (OUT / "PAGE_CHECK.md").write_text("".join(L), encoding="utf-8")
    print(f"\n{len(want)}本 → workspace/gsc/PAGE_CHECK.md")


if __name__ == "__main__":
    main()
