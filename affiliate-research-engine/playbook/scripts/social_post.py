#!/usr/bin/env python3
"""
social_post.py
**承認済みの在庫だけ**を投稿する。生成はしない。

  python social_post.py --platform x            … 何を投稿するか出すだけ
  python social_post.py --platform x --approve  … 実際に投稿する

  python social_post.py --platform x --stock-id X-546-b
  python social_post.py --platform x --stock-id X-546-b --approve
      … **投稿するものを名指しする。** 手で1件だけ試すときはこちら

  python social_post.py --mark-posted TH-521-a --posted-id 1810...
      … Threads は手で貼ったあと、投稿IDを登録する

投稿の直前にもう一度ゲートを通す。承認から時間が経って記事が
変わっていることがあるため。**1回の実行で最大1件。**

**在庫の選び方は2つある。混ぜない。**
  - `--stock-id` … 名指し。手動テスト用。他の在庫には一切触らない
  - 名指し無し … 最古の approved を自動で選ぶ。**定期運用（cron）専用**

名指しの安全装置（2026-08-10に追加）:
  - 在庫が無ければ止まる／platform が違えば止まる／approved 以外なら止まる
  - `--approve` が無ければ**表示だけ**。1文字も送らない
  - 送る直前に stock_id・URL・文字数・本文全文と、その本文のハッシュを出す
  - **表示した本文と、実際に API へ渡す本文のハッシュが違えば送らない**
    （表示のあとにファイルが書き換わっていないかを、ディスクから読み直して見る）
  - 投稿が成功したときだけ posted。**API が失敗したら approved のまま**
"""
import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
import social_spec as ss
import social_gate as sg
import social_inventory as inv


def text_hash(text):
    """表示した本文と、送る本文が同じであることを見るためのハッシュ。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def pick_by_id(spec, platform, stock_id):
    """**名指しで1件だけ選ぶ。** 条件に合わなければ理由を返して止める。

    戻り値は (stock, 止める理由)。理由が空でなければ投稿してはいけない。
    """
    hit = [s for _, s in inv.all_stock(spec) if s["stock_id"] == stock_id]
    if not hit:
        return None, f"stock_id が無い: {stock_id}"
    if len(hit) > 1:
        return None, f"stock_id が重複している: {stock_id}（{len(hit)}件）"
    s = hit[0]
    if s["platform"] != platform:
        return None, (f"{stock_id} は {s['platform']} の在庫。"
                      f"--platform {platform} とは違う")
    if s["state"] != "approved":
        return None, f"{stock_id} は {s['state']}。approved 以外は投稿しない"
    return s, ""


def verify_unchanged(spec, s, shown_hash, sent_text):
    """**表示したものと、これから送るものが同じか。**

    表示のあとに在庫ファイルが書き換わっていないかも、ディスクから
    読み直して見る。戻り値は (送ってよいか, 理由)。
    """
    disk = inv.load(inv.stock_path(spec, s["platform"], s["article_id"],
                                   s["stock_id"].rsplit("-", 1)[1]))
    hs, hd = text_hash(sent_text), text_hash(disk["text"])
    if hs != shown_hash or hd != shown_hash:
        return False, ("**表示した本文と送る本文が一致しない。**\n"
                       f"  表示  {shown_hash}\n  送る  {hs}\n  在庫  {hd}")
    if disk["state"] != s["state"]:
        return False, f"表示後に状態が変わった: {s['state']} → {disk['state']}"
    if inv.content_hash(s["thread_parts"]) != s["content_hash"]:
        return False, "在庫の content_hash が本文と合わない"
    return True, ""


def show_before_post(s, platform, spec):
    """**送る直前の表示。** ここに出したものだけが送られる。"""
    n = len(s["text"])
    w = sg.weighted_len(spec, s["text"]) if platform == "x" else None
    h = text_hash(s["text"])
    print("── 投稿するもの ──────────────────────────────")
    print(f"stock_id     : {s['stock_id']}")
    print(f"platform     : {platform}")
    print(f"記事         : {s['article_id']} {s['article_title']}")
    print(f"URL          : {s['article_url']}")
    print(f"文字数       : {n}" + (f"（Xの加重 {w}）" if w is not None else ""))
    print(f"本文ハッシュ : {h}")
    print("── 本文全文 ──────────────────────────────────")
    print(s["text"])
    print("──────────────────────────────────────────────")
    return h


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
    ap.add_argument("--stock-id", default="",
                    help="投稿する在庫を名指しする（手動テスト用）。"
                         "省略すると最古の approved を自動で選ぶ（定期運用用）")
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

    if a.stock_id:
        # **名指し。** 他の在庫は読むだけで、触らない
        s, why = pick_by_id(spec, a.platform, a.stock_id)
        if why:
            print(f"投稿しない: {why}")
            sys.exit(1)
        print(f"名指しで選んだ: {s['stock_id']}（記事 {s['article_id']}）\n")
    else:
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

    # ── 送る直前の表示と、その本文の固定 ─────────────────
    shown_hash = show_before_post(s, a.platform, spec)
    sent_text = s["text"]

    ok, why = verify_unchanged(spec, s, shown_hash, sent_text)
    if not ok:
        print(f"\n投稿しない: {why}")
        sys.exit(1)

    # **API を呼ぶ前に状態を進めない。** 進めてから失敗すると、
    # 投稿していないのに approved でなくなる（要件: 失敗時は approved のまま）
    try:
        pid = post_to_x(sent_text)
    except Exception as e:
        # **失敗しても作り直さない。状態も動かさない。** 理由だけ残して人が見る
        s["last_error"] = str(e)[:300]
        s["last_error_at"] = inv.now()
        inv.save(spec, s)      # state は approved のまま
        inv.append_history(spec, a.platform, {
            "stock_id": s["stock_id"], "article_id": s["article_id"],
            "posted_at": inv.now(), "text": sent_text,
            "content_hash": s["content_hash"],
            "idempotency_key": inv.idempotency_key(s),
            "result": "error", "error": str(e)[:300]})
        print(f"\n投稿に失敗した: {e}\n"
              f"{s['stock_id']} は approved のまま。再生成しない。")
        sys.exit(1)

    # ここから先は投稿が通ったあと。**成功したときだけ posted へ動かす**
    inv.transition(spec, s, "scheduled", scheduled_at=inv.now())
    inv.transition(spec, s, "posted", posted_at=inv.now(), posted_id=pid)
    inv.save(spec, s)
    inv.append_history(spec, a.platform, {
        "stock_id": s["stock_id"], "article_id": s["article_id"],
        "posted_id": pid, "posted_at": s["posted_at"], "text": s["text"],
        "content_hash": s["content_hash"],
        "idempotency_key": inv.idempotency_key(s), "result": "ok",
        "selected_by": "stock_id" if a.stock_id else "oldest_approved",
        "how": "social_post.py"})
    print(f"\n投稿した: {pid}")
    print(f"URL: https://x.com/sakura_eigo30/status/{pid}")


if __name__ == "__main__":
    main()
