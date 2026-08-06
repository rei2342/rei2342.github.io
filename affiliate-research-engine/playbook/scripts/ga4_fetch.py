#!/usr/bin/env python3
"""
ga4_fetch.py
Google アナリティクス(GA4)から、記事ごとのアクセスと流入元を取る。

Search Console は「Google検索から来た数」しか出さない。
Threads や X から来た読者は Search Console には1件も現れない。
SNSから記事に着地したかを見られるのは GA4 のほうなので、こちらを繋ぐ。

必要なもの:
  GSC_SERVICE_ACCOUNT_JSON … Search Consoleと同じサービスアカウントの鍵でよい
  そのサービスアカウントのメールアドレスを、GA4 の
  管理 → プロパティのアクセス管理 → 「閲覧者」で追加しておくこと

  GA4_PROPERTY_ID … 省略可。省略した場合は権限のあるプロパティを自動で探す
"""
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import requests
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import service_account

SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]
ADMIN = "https://analyticsadmin.googleapis.com/v1beta"
DATA = "https://analyticsdata.googleapis.com/v1beta"

DAYS = int(os.environ.get("DAYS", "7"))
OUT = Path("affiliate-research-engine/playbook/workspace/ga4")

# SNS由来だと分かる参照元。utm_source を付けて投稿しているものと、
# アプリ内ブラウザから素で来るドメインの両方を拾う。
SOCIAL = ("threads", "x", "twitter", "t.co", "note", "l.threads", "instagram", "facebook")


def creds():
    raw = os.environ.get("GSC_SERVICE_ACCOUNT_JSON", "")
    if not raw:
        print("GSC_SERVICE_ACCOUNT_JSON が未設定")
        sys.exit(1)
    info = json.loads(raw)
    c = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    c.refresh(GoogleRequest())
    return c, info.get("client_email", "(不明)")


def find_property(tok, email):
    """権限のあるGA4プロパティを探す。無ければ何をすればよいかを出して終わる。"""
    pid = os.environ.get("GA4_PROPERTY_ID", "").strip()
    if pid:
        return re.sub(r"\D", "", pid)

    r = requests.get(f"{ADMIN}/accountSummaries",
                     headers={"Authorization": f"Bearer {tok}"}, timeout=40)
    if r.status_code != 200:
        print(f"プロパティ一覧を取れない {r.status_code}: {r.text[:300]}")
        print(f"\nGA4の 管理 → プロパティのアクセス管理 で、{email} を「閲覧者」で追加してください。")
        sys.exit(1)

    props = []
    for a in r.json().get("accountSummaries", []):
        for p in a.get("propertySummaries", []):
            props.append((p.get("property", ""), p.get("displayName", "")))
    if not props:
        print(f"見えるプロパティが0件です。")
        print(f"GA4の 管理 → プロパティのアクセス管理 で、{email} を「閲覧者」で追加してください。")
        sys.exit(1)

    for path, name in props:
        print(f"見つかったプロパティ: {name} ({path})")
    # 複数あるときは先頭を使う。取り違えたら GA4_PROPERTY_ID で明示する
    return props[0][0].split("/")[-1]


def properties(tok):
    """権限のあるプロパティと、そのデータストリームを列挙する。

    プロパティ名だけでは、どのサイトを計測しているのか分からない。
    実際に0件だったとき「タグが動いていない」のか
    「別のプロパティを見ている」のかを切り分けるために要る。
    """
    r = requests.get(f"{ADMIN}/accountSummaries",
                     headers={"Authorization": f"Bearer {tok}"}, timeout=40)
    if r.status_code != 200:
        return []
    out = []
    for a in r.json().get("accountSummaries", []):
        for p in a.get("propertySummaries", []):
            path = p.get("property", "")
            s = requests.get(f"{ADMIN}/{path}/dataStreams",
                             headers={"Authorization": f"Bearer {tok}"}, timeout=40)
            streams = []
            if s.status_code == 200:
                for st in s.json().get("dataStreams", []):
                    w = st.get("webStreamData", {})
                    streams.append((w.get("defaultUri", "(URLなし)"),
                                    w.get("measurementId", "-")))
            out.append((path.split("/")[-1], p.get("displayName", ""), streams))
    return out


def realtime(tok, pid):
    """いまサイトを見ている人数。タグが動いているかの一番速い確認方法。"""
    r = requests.post(f"{DATA}/properties/{pid}:runRealtimeReport",
                      headers={"Authorization": f"Bearer {tok}"},
                      json={"metrics": [{"name": "activeUsers"}]}, timeout=40)
    if r.status_code != 200:
        return None
    rows = r.json().get("rows", [])
    return int(rows[0]["metricValues"][0]["value"]) if rows else 0


def report(tok, pid, dims, mets, days=None, limit=50, order=None, filters=None):
    body = {
        "dateRanges": [{"startDate": f"{days or DAYS}daysAgo", "endDate": "today"}],
        "dimensions": [{"name": d} for d in dims],
        "metrics": [{"name": m} for m in mets],
        "limit": limit,
    }
    if order:
        body["orderBys"] = [{"metric": {"metricName": order}, "desc": True}]
    if filters:
        body["dimensionFilter"] = filters
    r = requests.post(f"{DATA}/properties/{pid}:runReport",
                      headers={"Authorization": f"Bearer {tok}"},
                      json=body, timeout=60)
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}: {r.text[:300]}"
    rows = []
    for row in r.json().get("rows", []):
        rows.append(
            [d.get("value", "") for d in row.get("dimensionValues", [])]
            + [m.get("value", "") for m in row.get("metricValues", [])]
        )
    return rows, None


def table(header, rows, empty="（データなし）"):
    if not rows:
        return f"{empty}\n\n"
    s = "| " + " | ".join(header) + " |\n"
    s += "|" + "---|" * len(header) + "\n"
    for r in rows:
        s += "| " + " | ".join(str(c) for c in r) + " |\n"
    return s + "\n"


def main():
    c, email = creds()
    tok = c.token
    pid = find_property(tok, email)
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()

    L = [f"# GA4 アクセス {stamp}\n\n",
         f"プロパティ {pid} / 直近{DAYS}日（当日を含む・当日分は確定前）\n\n"]

    # 全体。まず母数が分からないと、個別の数字が多いのか少ないのか判断できない
    rows, err = report(tok, pid, [], ["sessions", "activeUsers", "screenPageViews"])
    empty = False
    if err:
        L.append(f"取得できない: {err}\n\n")
    elif rows and rows[0][0] != "0":
        s, u, v = rows[0]
        L.append(f"- セッション **{s}** / ユーザー **{u}** / ページビュー **{v}**\n\n")
    else:
        empty = True

    # 0件は「誰も来なかった」ではなく「計測できていない」ことが多い。
    # 見ているプロパティが正しいか、タグが動いているかをここで切り分ける。
    if empty:
        L.append("## ⚠️ 直近の計測が0件\n\n"
                 "「誰も来なかった」ではなく「計測できていない」可能性が高い。以下で切り分ける。\n\n")

        # もっと長い期間ならデータがあるか（タグ設置が最近なだけ、を除外する）
        long_rows, _ = report(tok, pid, [], ["sessions"], days=365)
        total = long_rows[0][0] if long_rows else "0"
        L.append(f"- **過去365日の合計セッション: {total}**"
                 + ("（このプロパティには一度もデータが入っていない）\n"
                    if total == "0" else "（過去にはデータがある。直近だけ止まっている）\n"))

        live = realtime(tok, pid)
        if live is not None:
            L.append(f"- **いまサイトを見ている人: {live}人**"
                     + ("（サイトを開いた状態でこれが0なら、タグが動いていない）\n"
                        if live == 0 else "（タグは動いている）\n"))

        L.append("\n### 権限のあるプロパティとデータストリーム\n\n"
                 "| プロパティID | 名前 | 計測しているURL | 測定ID |\n|---|---|---|---|\n")
        for prop_id, name, streams in properties(tok):
            mark = " ←取得中" if prop_id == str(pid) else ""
            if not streams:
                L.append(f"| {prop_id}{mark} | {name} | （ストリームなし） | - |\n")
            for uri, mid in streams:
                L.append(f"| {prop_id}{mark} | {name} | {uri} | {mid} |\n")
        L.append("\nsakura-eigo.com を計測しているプロパティが別にあれば、"
                 "そのIDを Secret `GA4_PROPERTY_ID` に入れてください。\n\n")

    # 流入元。Threadsから来ているかはここで分かる
    L.append("## 流入元\n\n")
    rows, err = report(tok, pid, ["sessionSource", "sessionMedium"],
                       ["sessions", "activeUsers"], order="sessions")
    L.append(err + "\n\n" if err else
             table(["参照元", "メディア", "セッション", "ユーザー"], rows))

    # 着地ページ×流入元。「Threadsから、どの記事に降りたか」がこれ
    L.append("## 着地ページ × 流入元\n\n")
    rows, err = report(tok, pid, ["landingPagePlusQueryString", "sessionSource"],
                       ["sessions"], limit=100, order="sessions")
    if err:
        L.append(err + "\n\n")
    else:
        L.append(table(["着地ページ", "参照元", "セッション"],
                       [[r[0][:70], r[1], r[2]] for r in rows]))

        social = [r for r in rows if any(s in r[1].lower() for s in SOCIAL)]
        L.append("### そのうちSNS由来だけ\n\n")
        L.append(table(["着地ページ", "参照元", "セッション"],
                       [[r[0][:70], r[1], r[2]] for r in social],
                       empty="**SNSからの着地は0件**。投稿は見られていても記事までは来ていない。\n\n"))

    # 記事別。読まれている記事が分かれば、次に書く軸も決められる
    L.append("## ページ別 上位20\n\n")
    rows, err = report(tok, pid, ["pagePath"],
                       ["screenPageViews", "sessions", "userEngagementDuration"],
                       limit=20, order="screenPageViews")
    if err:
        L.append(err + "\n\n")
    else:
        out = []
        for p, v, s, eng in rows:
            # 滞在は秒で返る。読了の目安にするので分に直す
            mins = f"{int(eng) / max(int(s), 1) / 60:.1f}分" if eng.isdigit() else "-"
            out.append([v, s, mins, p[:60]])
        L.append(table(["PV", "セッション", "平均滞在", "ページ"], out))

    text = "".join(L)
    (OUT / f"{stamp}.md").write_text(text, encoding="utf-8")
    (OUT / "LATEST.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
