#!/usr/bin/env python3
"""
threads_insights.py
Threadsの投稿ごとの数字を取得して記録する。

投稿直後の数字は当てにならない（昨日11だった投稿が翌日34になった実例がある）。
毎日取って履歴を残し、24時間・48時間・7日で見比べられるようにする。

必要なもの:
  THREADS_ACCESS_TOKEN  … Threads APIの長期アクセストークン（60日程度で失効）
  THREADS_USER_ID       … 自分のThreadsユーザーID（省略時は me を使う）
"""
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import requests

API = "https://graph.threads.net/v1.0"
TOKEN = os.environ.get("THREADS_ACCESS_TOKEN", "")
USER = os.environ.get("THREADS_USER_ID", "me")
LIMIT = int(os.environ.get("LIMIT", "25"))
OUT = Path("affiliate-research-engine/playbook/workspace/threads_insights")

# 投稿ごとに取れる指標。取れないものがあっても止めない。
METRICS = ["views", "likes", "replies", "reposts", "quotes"]


def get(path, **params):
    params["access_token"] = TOKEN
    r = requests.get(f"{API}/{path}", params=params, timeout=40)
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}: {r.text[:200]}"
    return r.json(), None


def main():
    if not TOKEN:
        print("THREADS_ACCESS_TOKEN が未設定。")
        print("Metaの開発者アプリでThreadsを連携し、長期トークンを取得してください。")
        sys.exit(1)

    posts, err = get(f"{USER}/threads",
                     fields="id,text,timestamp,permalink,media_type",
                     limit=LIMIT)
    if err:
        print(f"投稿一覧を取得できない: {err}")
        sys.exit(1)

    rows = []
    for p in posts.get("data", []):
        ins, err = get(f"{p['id']}/insights", metric=",".join(METRICS))
        vals = {}
        if ins:
            for m in ins.get("data", []):
                # 単一値は values[0].value、期間ものは total_value.value に入る
                v = None
                if m.get("values"):
                    v = m["values"][0].get("value")
                elif m.get("total_value"):
                    v = m["total_value"].get("value")
                vals[m.get("name")] = v
        elif err:
            vals["_error"] = err

        text = re.sub(r"\s+", " ", (p.get("text") or ""))[:42]
        rows.append({
            "id": p["id"],
            "posted_at": p.get("timestamp", ""),
            "text": text,
            "permalink": p.get("permalink", ""),
            **{m: vals.get(m) for m in METRICS},
        })

    now = datetime.now(timezone.utc).isoformat()
    stamp = date.today().isoformat()
    OUT.mkdir(parents=True, exist_ok=True)

    # 履歴を積む。同じ投稿を毎日測って伸びを見るため、上書きしない。
    hist_path = OUT / "history.jsonl"
    with open(hist_path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({"measured_at": now, **r}, ensure_ascii=False) + "\n")

    L = [f"# Threads 数字 {stamp}\n\n",
         f"取得 {len(rows)}件（測定時刻 {now}）\n\n",
         "| 表示 | いいね | 返信 | 再投稿 | 引用 | 投稿日 | 本文 |\n",
         "|---|---|---|---|---|---|---|\n"]
    for r in sorted(rows, key=lambda x: -(x.get("views") or 0)):
        L.append(f"| {r.get('views') or '-'} | {r.get('likes') or '-'} | "
                 f"{r.get('replies') or '-'} | {r.get('reposts') or '-'} | "
                 f"{r.get('quotes') or '-'} | {r['posted_at'][:10]} | {r['text']} |\n")

    (OUT / f"{stamp}.md").write_text("".join(L), encoding="utf-8")
    (OUT / "LATEST.md").write_text("".join(L), encoding="utf-8")
    print("".join(L))


if __name__ == "__main__":
    main()
