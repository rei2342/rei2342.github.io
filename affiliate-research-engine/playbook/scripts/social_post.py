#!/usr/bin/env python3
"""
social_post.py
**承認済みの在庫だけ**を投稿する。生成はしない。

  python social_post.py --platform x            … 何を投稿するか出すだけ
  python social_post.py --platform x --approve  … 実際に投稿する

  python social_post.py --mark-posted TH-521-a --posted-id 1810...
      … Threads は手で貼ったあと、投稿IDを登録する

投稿の直前にもう一度ゲートを通す。承認から時間が経って記事が
変わっていることがあるため。**1回の実行で最大1件。**
"""
import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
import social_spec as ss
import social_gate as sg
import social_inventory as inv


def post_to_x(text):
    import tweepy
    c = tweepy.Client(
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"])
    return str(c.create_tweet(text=text).data["id"])


def mark_posted(spec, sid, posted_id):
    hit = [(p, s) for p, s in inv.all_stock(spec) if s["stock_id"] == sid]
    if not hit:
        print(f"見つからない: {sid}")
        sys.exit(1)
    _, s = hit[0]
    if s["state"] not in ("approved", "scheduled"):
        print(f"{sid} は {s['state']}。承認済みでないものは記録しない")
        sys.exit(1)
    if s["state"] == "approved":
        inv.transition(spec, s, "scheduled", scheduled_at=inv.now())
    inv.transition(spec, s, "posted", posted_at=inv.now(), posted_id=posted_id)
    inv.save(spec, s)
    inv.append_history(spec, s["platform"], {
        "stock_id": sid, "article_id": s["article_id"],
        "posted_id": posted_id, "posted_at": s["posted_at"],
        "text": s["text"], "content_hash": s["content_hash"],
        "idempotency_key": inv.idempotency_key(s), "result": "ok",
        "how": "手で貼った"})
    print(f"{sid} → posted（{posted_id}）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", choices=["x", "threads"], default="x")
    ap.add_argument("--approve", action="store_true")
    ap.add_argument("--mark-posted", default="")
    ap.add_argument("--posted-id", default="")
    a = ap.parse_args()
    spec = ss.load_spec()

    if a.mark_posted:
        if not a.posted_id:
            print("--posted-id が要る")
            sys.exit(1)
        mark_posted(spec, a.mark_posted, a.posted_id)
        return

    if a.platform == "threads":
        print("Threads は投稿用トークンが無い。手で貼ってから "
              "--mark-posted で登録する。")
        sys.exit(1)

    ready = [(p, s) for p, s in inv.all_stock(spec, a.platform)
             if s["state"] == "approved"]
    if not ready:
        print("承認済みの在庫が無い。**投稿しない。**")
        return
    # 1回の実行で1件だけ。まとめて出さない
    _, s = sorted(ready, key=lambda x: x[1]["approved_at"] or "")[0]
    print(f"次に出すもの: {s['stock_id']}（記事 {s['article_id']}）\n")
    print(s["text"])

    if inv.already_posted(spec, s):
        print("\n**同じ内容を投稿済み**（idempotency key が一致）。中止する。")
        sys.exit(1)

    # 承認から時間が経っている。記事が変わっていないかもう一度見る
    import social_generate as gen
    art = gen.fetch_article(s["article_id"]) if a.approve else None
    if a.approve:
        if not art:
            print("\n記事を取得できない。中止する。")
            sys.exit(1)
        res = sg.run_gates(spec, a.platform, s["thread_parts"], art,
                           history=inv.read_history(
                               spec, a.platform,
                               spec["duplicate"]["window_days"]),
                           stock_modified=s.get("article_modified_gmt"))
        if not sg.passed(res):
            inv.transition(spec, s, "stale")
            s["gate_results"] = [{"id": g, "ok": ok, "detail": d}
                                 for g, ok, d in res]
            inv.save(spec, s)
            print("\n投稿直前のゲートで落ちた。stale へ戻す。\n" + sg.fmt(res))
            sys.exit(1)

    if not a.approve:
        print("\n--approve が無いので、ここで終わり。**投稿していない。**")
        return

    inv.transition(spec, s, "scheduled", scheduled_at=inv.now())
    inv.save(spec, s)
    try:
        pid = post_to_x(s["text"])
    except Exception as e:
        # **失敗しても作り直さない。** 理由を残して人が見る
        s["last_error"] = str(e)[:300]
        inv.transition(spec, s, "stale")
        inv.save(spec, s)
        inv.append_history(spec, a.platform, {
            "stock_id": s["stock_id"], "article_id": s["article_id"],
            "posted_at": inv.now(), "text": s["text"],
            "content_hash": s["content_hash"],
            "idempotency_key": inv.idempotency_key(s),
            "result": "error", "error": str(e)[:300]})
        print(f"\n投稿に失敗した: {e}\n在庫を stale にして止める。再生成しない。")
        sys.exit(1)

    inv.transition(spec, s, "posted", posted_at=inv.now(), posted_id=pid)
    inv.save(spec, s)
    inv.append_history(spec, a.platform, {
        "stock_id": s["stock_id"], "article_id": s["article_id"],
        "posted_id": pid, "posted_at": s["posted_at"], "text": s["text"],
        "content_hash": s["content_hash"],
        "idempotency_key": inv.idempotency_key(s), "result": "ok",
        "how": "social_post.py"})
    print(f"\n投稿した: {pid}")


if __name__ == "__main__":
    main()
