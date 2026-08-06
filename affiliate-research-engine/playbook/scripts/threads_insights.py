#!/usr/bin/env python3
"""
threads_insights.py
Threadsの投稿ごとの数字を取得して記録する。

投稿直後の数字は当てにならない（昨日11だった投稿が翌日34になった実例がある）。
毎日取って履歴を残し、24時間・48時間・7日で見比べられるようにする。

複数アカウントをまとめて取れる。コードは共通で、トークンだけアカウントごとに要る
（Metaのアプリは1つでよく、認可をアカウントの数だけ行う）。

必要なもの（どちらか）:
  THREADS_ACCOUNTS      … [{"name":"さくら","token":"..."}, ...] のJSON
  THREADS_ACCESS_TOKEN  … 1アカウントだけのとき。name は「さくら」になる

トークンは60日程度で失効するので、切れたらそのアカウントだけ理由を出して続行する。
"""
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import requests

API = "https://graph.threads.net/v1.0"
LIMIT = int(os.environ.get("LIMIT", "25"))
OUT = Path("affiliate-research-engine/playbook/workspace/threads_insights")

# 投稿ごとに取れる指標。取れないものがあっても止めない。
METRICS = ["views", "likes", "replies", "reposts", "quotes"]


def accounts():
    """アカウント一覧を返す。複数指定が無ければ単一トークンとして扱う。"""
    raw = os.environ.get("THREADS_ACCOUNTS", "").strip()
    if raw:
        try:
            return [a for a in json.loads(raw) if a.get("token")]
        except Exception as e:
            print(f"THREADS_ACCOUNTS を読めない: {e}")
            sys.exit(1)
    tok = os.environ.get("THREADS_ACCESS_TOKEN", "").strip()
    return [{"name": "さくら", "token": tok}] if tok else []


def get(token, path, **params):
    params["access_token"] = token
    r = requests.get(f"{API}/{path}", params=params, timeout=40)
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}: {r.text[:200]}"
    return r.json(), None


def whoami(token):
    """トークンが実際にどのアカウントのものかを確かめる。

    生成ツールをブラウザで操作すると、ログイン中のアカウントに
    引っ張られて別アカウントのトークンが出ることがある。
    2026-08-06に、さくらとAKIRAの両方がAKIRAのトークンになっていた。
    設定した名前を信用せず、APIに聞く。
    """
    me, err = get(token, "me", fields="id,username")
    if err:
        return None, None
    return me.get("id"), me.get("username")


def collect(acc):
    """1アカウントぶんの投稿と数字を集める。"""
    token = acc["token"]
    user = acc.get("user_id", "me")
    acc["actual_id"], acc["actual_name"] = whoami(token)
    posts, err = get(token, f"{user}/threads",
                     fields="id,text,timestamp,permalink,media_type", limit=LIMIT)
    if err:
        return [], err

    rows = []
    for p in posts.get("data", []):
        ins, ierr = get(token, f"{p['id']}/insights", metric=",".join(METRICS))
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
        text = re.sub(r"\s+", " ", (p.get("text") or ""))[:42]
        rows.append({
            "account": acc["name"],
            # 履歴を後から見るとき、設定名が正しかったか確かめられるように残す
            "account_actual": acc.get("actual_name"),
            "id": p["id"],
            "posted_at": p.get("timestamp", ""),
            "text": text,
            "permalink": p.get("permalink", ""),
            **{m: vals.get(m) for m in METRICS},
        })
    return rows, None


def main():
    accs = accounts()
    if not accs:
        print("トークンが未設定。THREADS_ACCOUNTS か THREADS_ACCESS_TOKEN を設定してください。")
        sys.exit(1)

    now = datetime.now(timezone.utc).isoformat()
    stamp = date.today().isoformat()
    OUT.mkdir(parents=True, exist_ok=True)

    all_rows, failed = [], []
    for acc in accs:
        rows, err = collect(acc)
        if err:
            # 1アカウントのトークン切れで全部を止めない
            print(f"[{acc['name']}] 取得できない: {err}")
            failed.append((acc["name"], err))
            continue
        print(f"[{acc['name']}] {len(rows)}件")
        all_rows += rows

    if all_rows:
        # 同じ投稿を毎日測って伸びを見るため、上書きせず追記する
        with open(OUT / "history.jsonl", "a", encoding="utf-8") as f:
            for r in all_rows:
                f.write(json.dumps({"measured_at": now, **r}, ensure_ascii=False) + "\n")

    L = [f"# Threads 数字 {stamp}\n\n",
         f"測定 {now}\n\n"]

    if failed:
        L.append("## 取得できなかったアカウント\n\n")
        for name, err in failed:
            L.append(f"- **{name}**: {err}\n")
        L.append("\nトークンは60日程度で失効します。切れていれば取り直してください。\n\n")

    # 同じトークンを2つ登録すると、数字が二重に並ぶだけで誰も気づかない。
    # 実IDが重複していたら、集計より先に警告を出す。
    seen = {}
    for acc in accs:
        aid = acc.get("actual_id")
        if not aid:
            continue
        seen.setdefault(aid, []).append(acc)
    dupes = [v for v in seen.values() if len(v) > 1]
    if dupes:
        L.append("## ⚠️ 同じアカウントのトークンが重複しています\n\n")
        for group in dupes:
            names = " / ".join(a["name"] for a in group)
            L.append(f"- **{names}** はどれも `@{group[0].get('actual_name')}` のトークンです\n")
        L.append("\n取り違えた側のトークンを生成し直してください。"
                 "以下の数字は重複したまま並んでいます。\n\n")

    # アカウントごとの合計。横並びで比べられるようにする
    if len(accs) > 1:
        L.append("## アカウント別の合計\n\n"
                 "| 設定名 | 実際のアカウント | 投稿 | 表示 | いいね | 返信 |\n"
                 "|---|---|---|---|---|---|\n")
        for acc in accs:
            rs = [r for r in all_rows if r["account"] == acc["name"]]
            if not rs:
                continue
            tot = lambda k: sum(r.get(k) or 0 for r in rs)
            L.append(f"| {acc['name']} | @{acc.get('actual_name') or '不明'} | "
                     f"{len(rs)} | {tot('views')} | "
                     f"{tot('likes')} | {tot('replies')} |\n")
        L.append("\n")

    L.append("## 投稿別（表示の多い順）\n\n")
    L.append("| 表示 | いいね | 返信 | 再投稿 | 引用 | 投稿日 | アカウント | 本文 |\n")
    L.append("|---|---|---|---|---|---|---|---|\n")
    for r in sorted(all_rows, key=lambda x: -(x.get("views") or 0)):
        L.append(f"| {r.get('views') or '-'} | {r.get('likes') or '-'} | "
                 f"{r.get('replies') or '-'} | {r.get('reposts') or '-'} | "
                 f"{r.get('quotes') or '-'} | {r['posted_at'][:10]} | "
                 f"{r['account']} | {r['text']} |\n")

    (OUT / f"{stamp}.md").write_text("".join(L), encoding="utf-8")
    (OUT / "LATEST.md").write_text("".join(L), encoding="utf-8")
    print("".join(L))

    # 全アカウントが取れなかったときだけ失敗にする
    if failed and not all_rows:
        sys.exit(1)


if __name__ == "__main__":
    main()
