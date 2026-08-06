#!/usr/bin/env python3
"""
daily_patrol.py
Threadsの数字とサイトの数字を1枚にまとめる。

これまでは Threads のレポートと GA4 のレポートを人間が突き合わせていた。
それだと「表示は伸びたが記事に来ていない」のか「そもそも表示が出ていない」のかを
判断するのに毎回手間がかかる。1枚に並べれば1回で分かる。

見るのは3段。ここが落ちている段が、次に直す場所になる。
  表示（Threads） → 着地（GA4） → アフィリンクのクリック（GA4のclickイベント）

2026-08-05の実測では、780表示に対して記事への遷移がほぼ0だった。
表示が伸びても遷移しないことがあるので、表示だけを見て良し悪しを言わない。
"""
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import ga4_fetch as g4

DAYS = int(os.environ.get("DAYS", "14"))
HISTORY = Path("affiliate-research-engine/playbook/workspace/threads_insights/history.jsonl")
OUT = Path("affiliate-research-engine/playbook/workspace/patrol")

# 投稿に付けている印。どの経路から来たかを分ける
SOCIAL_SOURCES = ("threads", "x", "note")
AFFILIATE_DOMAINS = ("af.moshimo.com", "px.a8.net")


def latest_threads_posts():
    """history.jsonl から、投稿ごとの最新の測定値を取る。

    毎日追記しているので同じ投稿が何行も入っている。
    伸びを見るのは別の話で、ここでは今の値だけが要る。
    """
    if not HISTORY.exists():
        return []
    latest = {}
    for line in HISTORY.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        key = (r.get("account"), r.get("id"))
        prev = latest.get(key)
        if not prev or r.get("measured_at", "") > prev.get("measured_at", ""):
            latest[key] = r
    cutoff = (datetime.now(timezone.utc) - timedelta(days=DAYS)).isoformat()
    return [r for r in latest.values() if (r.get("posted_at") or "") >= cutoff]


def table(header, rows, empty="（データなし）\n\n"):
    if not rows:
        return empty
    s = "| " + " | ".join(header) + " |\n" + "|" + "---|" * len(header) + "\n"
    for r in rows:
        s += "| " + " | ".join(str(c) for c in r) + " |\n"
    return s + "\n"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()
    L = [f"# 日次パトロール {stamp}\n\n直近{DAYS}日\n\n"]

    # ── 1段目: Threadsで何人に見られたか ──
    posts = latest_threads_posts()
    L.append("## ① Threads（表示された数）\n\n")
    if not posts:
        L.append("履歴がまだ無い。`threads-insights` を先に回す。\n\n")
    else:
        rows = [[p.get("views") or 0, p.get("likes") or "-", p.get("replies") or "-",
                 (p.get("posted_at") or "")[:10], p.get("account"), p.get("text", "")[:34]]
                for p in sorted(posts, key=lambda x: -(x.get("views") or 0))]
        L.append(table(["表示", "いいね", "返信", "投稿日", "アカウント", "本文"], rows))

    # ── 2段目・3段目: サイト側 ──
    try:
        c, email = g4.creds()
        tok = c.token
        pid = g4.find_property(tok, email)
    except SystemExit:
        L.append("## ②③ サイト側\n\nGA4に接続できない。権限とSecretを確認する。\n")
        (OUT / "PATROL.md").write_text("".join(L), encoding="utf-8")
        print("".join(L))
        return

    L.append(f"## ② 記事に着地した数（GA4 / プロパティ{pid}）\n\n")

    rows, err = g4.report(tok, pid, ["sessionSource"], ["sessions"],
                          days=DAYS, order="sessions")
    if err:
        L.append(err + "\n\n")
        rows = []
    social = [r for r in rows if any(s in r[0].lower() for s in SOCIAL_SOURCES)]
    total_social = sum(int(r[1]) for r in social)
    total_all = sum(int(r[1]) for r in rows)

    L.append(f"- 全流入 **{total_all}** セッション / うちSNS由来 **{total_social}**\n\n")
    L.append(table(["参照元", "セッション"], social,
                   empty="**SNS由来の着地は0件**。投稿は見られていても記事までは来ていない。\n\n"))

    # 遷移率。表示に対して何%が記事まで来たか。ここが今いちばん見たい数字
    views = sum(p.get("views") or 0 for p in posts)
    if views:
        rate = total_social / views * 100
        L.append(f"**表示{views} → 着地{total_social}（{rate:.2f}%）**\n\n")
        if rate < 1:
            L.append("遷移率が1%未満。表示は出ているが記事に来ていない。\n"
                     "リンクの置き場所と、2投稿目の終わり方を疑う。\n\n")

    # どの記事に降りたか。次に書く軸を決める材料になる
    rows, err = g4.report(tok, pid, ["landingPagePlusQueryString"], ["sessions"],
                          days=DAYS, limit=20, order="sessions")
    L.append("### 着地ページ 上位\n\n")
    L.append(err + "\n\n" if err else
             table(["着地ページ", "セッション"], [[r[0][:64], r[1]] for r in rows]))

    # ── 3段目: アフィリンクのクリック ──
    L.append("## ③ アフィリエイトリンクのクリック\n\n")
    rows, err = g4.report(
        tok, pid, ["customEvent:link_domain"], ["eventCount"],
        days=DAYS, limit=30, order="eventCount",
        filters={"filter": {"fieldName": "eventName",
                            "stringFilter": {"value": "click"}}})
    if err:
        # カスタムディメンション未登録だとここで落ちる。設定漏れを名指しする
        L.append("取得できない。GA4でカスタムディメンション `link_domain`\n"
                 "（範囲=イベント / パラメータ=link_domain）を登録すると出る。\n"
                 "登録より前のクリックは対象にならないので、早いほど良い。\n\n"
                 f"（詳細: {err}）\n\n")
    else:
        af = [r for r in rows if any(d in r[0] for d in AFFILIATE_DOMAINS)]
        L.append(table(["クリック先", "回数"], af,
                       empty="**アフィリエイトリンクのクリックは0件。**\n"
                             "記事には来ていてもリンクは踏まれていない。\n\n"))
        if rows:
            L.append("<details><summary>外部リンク全体</summary>\n\n"
                     + table(["クリック先", "回数"], rows) + "</details>\n\n")

    L.append("---\n\n"
             "3段のどこで落ちているかで、次に直す場所が決まる。\n"
             "- ①が小さい → 投稿の入口（1行目・定説起点）\n"
             "- ①は出るが②が小さい → リンクの置き場所と2投稿目の終わり方\n"
             "- ②は来るが③が0 → 記事内のCTAの位置と、案件の選び方\n")

    text = "".join(L)
    (OUT / f"{stamp}.md").write_text(text, encoding="utf-8")
    (OUT / "PATROL.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
