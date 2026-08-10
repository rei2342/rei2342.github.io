#!/usr/bin/env python3
"""
social_approve.py
在庫を承認する／却下する／記事の改稿で古くなったものを戻す。

  python social_approve.py --list
  python social_approve.py --approve X-521-a
  python social_approve.py --reject TH-521-a --reason "手順が記事と違う"
  python social_approve.py --revoke X-521-a --reason "仕様が変わった"
  python social_approve.py --stale-check          # 記事が改稿されたものを戻す

**承認は取り消せる。** 仕様を変えたのに承認済みのまま残ると、
古い基準で通った文が投稿される。`--revoke` で awaiting_approval へ戻す。

**ここでも投稿はしない。** 投稿は social_post.py だけ。
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
import social_spec as ss
import social_inventory as inv
import social_gate as sg

REASONS = [
    "記事の内容と違う",
    "未確認の体験・数値が入っている",
    "読む理由が弱い",
    "記事へ送る一言が具体的でない",
    "他の投稿と似ている",
    "文体が合わない",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--approve", default="")
    ap.add_argument("--reject", default="")
    ap.add_argument("--revoke", default="",
                    help="承認を取り消して awaiting_approval へ戻す")
    ap.add_argument("--reason", default="")
    ap.add_argument("--stale-check", action="store_true")
    ap.add_argument("--stale", default="",
                    help="記事の改稿で古くなった在庫を stale へ戻す")
    a = ap.parse_args()
    spec = ss.load_spec()

    if a.list or not (a.approve or a.reject or a.revoke or a.stale
                      or a.stale_check):
        rows = inv.all_stock(spec)
        print(f"在庫 {len(rows)}件\n")
        print("| stock_id | 記事 | 状態 | 文字数 |")
        print("|---|---|---|---|")
        for _, s in rows:
            print(f"| {s['stock_id']} | {s['article_id']} "
                  f"{s['article_title'][:24]} | {s['state']} "
                  f"| {len(s['text'])} |")
        print("\n却下の理由に使えるもの: " + " / ".join(REASONS))
        return

    if a.stale_check:
        # 記事が改稿されたら、未投稿の在庫を stale へ戻す
        import social_generate as gen
        moved = []
        for p, s in inv.all_stock(spec):
            if s["state"] in ("posted", "rejected", "stale", "archived"):
                continue
            art = gen.fetch_article(s["article_id"])
            if not art:
                continue
            if art.get("modified_gmt") != s.get("article_modified_gmt"):
                inv.transition(spec, s, "stale")
                inv.save(spec, s)
                moved.append(s["stock_id"])
        print(f"stale へ戻した: {len(moved)}件 " + " ".join(moved))
        return

    sid = a.approve or a.reject or a.revoke or a.stale
    hit = [(p, s) for p, s in inv.all_stock(spec) if s["stock_id"] == sid]
    if not hit:
        print(f"見つからない: {sid}")
        sys.exit(1)
    _, s = hit[0]
    if a.approve:
        if any(not g["ok"] for g in s["gate_results"]):
            print("ゲートに落ちている在庫は承認できない")
            sys.exit(1)
        # **締めの型の偏りは承認で止める。** 1件ずつでは分からないので、
        # 同じ媒体の5件の窓で見る（2026-08-10に警告から昇格）
        peers = sorted([x for _, x in inv.all_stock(spec, s["platform"])
                        if x["state"] not in ("stale", "rejected", "archived")],
                       key=lambda y: y["article_id"])
        ok, why = sg.same_closer_gate(spec, peers)
        if not ok:
            print(f"承認できない: {why}")
            sys.exit(1)
        inv.transition(spec, s, "approved", approved_at=inv.now())
    elif a.stale:
        # 記事が改稿されたので、この在庫は最新本文に対応していない。
        # **消さない。** 旧本文・生成日時・旧 modified_gmt を残したまま退役させる
        import social_generate as gen
        art = inv.live_article(s["article_id"])
        inv.transition(
            spec, s, "stale",
            stale_reason="article_modified_after_generation",
            staled_at=inv.now(),
            superseded_text=s["text"],
            superseded_thread_parts=list(s["thread_parts"]),
            generated_at=s.get("created_at"),
            article_modified_gmt_at_generation=s.get("article_modified_gmt"),
            article_modified_gmt_now=(art or {}).get("modified_gmt"))
    elif a.revoke:
        # 承認を取り消す。**消さずに履歴へ残す。**
        # いつ・なぜ戻したかが追えないと、同じ文がまた承認される
        if not a.reason:
            print("--reason が要る（なぜ取り消すか）")
            sys.exit(1)
        inv.transition(spec, s, "awaiting_approval", approved_at=None,
                       revoked_reason=a.reason)
    else:
        if not a.reason:
            print("--reason が要る。候補: " + " / ".join(REASONS))
            sys.exit(1)
        inv.transition(spec, s, "rejected", rejected_reason=a.reason)
    inv.save(spec, s)
    print(f"{sid} → {s['state']}")


if __name__ == "__main__":
    main()
