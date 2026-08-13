#!/usr/bin/env python3
"""
social_post.py
**承認済みの在庫だけ**を投稿する。生成はしない。

  python social_post.py --platform x            … 何を投稿するか出すだけ
  python social_post.py --platform x --approve  … 実際に投稿する

  python social_post.py --platform x --stock-id X-546-b
  python social_post.py --platform x --stock-id X-546-b --approve
      … **投稿するものを名指しする。** 手で1件だけ試すときはこちら

  python social_post.py --platform threads --stock-id THREADS-546-b
      … Threads に貼る本文を、投稿する順に出す（投稿はしない）

  python social_post.py --mark-posted THREADS-546-b \
      --posted-url <親投稿のURL> --reply-url <返信のURL>
      … Threads は手で貼ったあと、貼った先のURLを登録する。
        2投稿構成なら親と返信の両方が要る

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


def check_url_live(text):
    """**本文に入っているURLを実際に叩く。** 200でなければ投稿しない。

    utm を足したときに、リダイレクトやクエリの取り違えで
    404 になっていないかを、送る前に見る。
    戻り値は (送ってよいか, 表示する行)。
    """
    import requests
    out, ok_all = [], True
    for u in sg.URL.findall(text):
        try:
            r = requests.get(u, timeout=20, allow_redirects=True,
                             headers={"User-Agent": "sakura-social-check"})
            ok = r.status_code == 200
            out.append(f"  {r.status_code} {u}"
                       + (f"  → {r.url}" if r.url != u else ""))
        except Exception as e:
            ok, out = False, out + [f"  取得できない {u}（{e}）"]
        ok_all = ok_all and ok
    if not out:
        return False, "  URLが無い"
    return ok_all, "\n".join(out)


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


POST_URL = re.compile(r"https?://(?:www\.)?threads\.(?:net|com)/[^\s]+")


def post_id_from_url(url):
    """Threadsの投稿URLからIDを取る。**種類も一緒に返す。**

    共有リンク（/share/<コード>）と投稿URL（/post/<コード>）は別物。
    共有リンクはリダイレクト先が本体なので、これを投稿IDだと言い切らない。
    戻り値は (コード, 種類)。取れなければ ("", "")。
    """
    m = re.search(r"/post/([A-Za-z0-9_\-]+)", url)
    if m:
        return m.group(1), "post_code"
    m = re.search(r"/share/([A-Za-z0-9_\-]+)", url)
    if m:
        return m.group(1), "share_code"
    return "", ""


def mark_posted(spec, sid, posted_id, posted_url="", reply_url=""):
    """**手で貼ったものを記録する。** 貼った先のURLまで残す。

    2投稿構成のときは、親投稿と返信の両方のURLが要る。
    どちらか片方だけだと、あとで「返信が本当にぶら下がったか」を
    誰も確かめられない。
    """
    hit = [(p, s) for p, s in inv.all_stock(spec) if s["stock_id"] == sid]
    if not hit:
        print(f"見つからない: {sid}")
        sys.exit(1)
    _, s = hit[0]
    if s["state"] not in ("approved", "scheduled"):
        print(f"{sid} は {s['state']}。承認済みでないものは記録しない")
        sys.exit(1)
    n = len(s["thread_parts"])
    if n > 1 and not (posted_url and reply_url):
        print(f"{sid} は{n}投稿構成。--posted-url（親）と --reply-url（返信）"
              f"の両方が要る")
        sys.exit(1)
    for label, u in (("親投稿", posted_url), ("返信", reply_url)):
        if u and not POST_URL.fullmatch(u):
            print(f"{label}のURLが Threads の投稿URLでない: {u}")
            sys.exit(1)
    if posted_url and posted_url == reply_url:
        print("親投稿と返信のURLが同じ。貼り間違いの可能性がある")
        sys.exit(1)
    pid, kind = post_id_from_url(posted_url)
    posted_id = posted_id or pid
    if not posted_id:
        print("投稿IDが決まらない。--posted-id を渡すか、"
              "/post/<コード> か /share/<コード> を含むURLを渡す")
        sys.exit(1)
    reply_id, reply_kind = post_id_from_url(reply_url)
    # **共有リンクは投稿URLそのものではない。** 記録では言い分ける
    canon = "取得済み" if kind == "post_code" else "未取得"

    if s["state"] == "approved":
        inv.transition(spec, s, "scheduled", scheduled_at=inv.now())
    inv.transition(spec, s, "posted", posted_at=inv.now(), posted_id=posted_id,
                   posted_url=posted_url or None, posted_id_kind=kind or None,
                   reply_id=reply_id or None, reply_url=reply_url or None,
                   reply_id_kind=reply_kind or None,
                   canonical_post_url=canon,
                   reply_attached_verified="未確認")
    inv.save(spec, s)
    inv.append_history(spec, s["platform"], {
        "stock_id": sid, "article_id": s["article_id"],
        "posted_id": posted_id, "posted_url": posted_url,
        "posted_id_kind": kind, "reply_id_kind": reply_kind,
        "reply_id": reply_id, "reply_url": reply_url,
        "posted_at": s["posted_at"],
        "text": s["text"], "content_hash": s["content_hash"],
        "idempotency_key": inv.idempotency_key(s), "result": "ok",
        "how": "手で貼った"})
    print(f"{sid} → posted（{posted_id}）")
    if posted_url:
        print(f"  親投稿 {posted_url}")
    if reply_url:
        print(f"  返信   {reply_url}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", choices=["x", "threads"], default="x")
    ap.add_argument("--approve", action="store_true",
                    help="人が承認して投稿する（workflow_dispatch 用）")
    # ★2026-08-13 追加。定期実行を「必ず投稿0」から戻すための機械承認。
    #   --approve は workflow_dispatch の inputs でしか渡せず、schedule では常に空。
    #   そのため 8/10 以降、定期実行は構造上100%投稿0だった。
    #   --auto はゲートを全部通ったものだけを1件投稿する。
    #   ゲートが1つでも落ちれば投稿しない（stale へ戻す）。
    ap.add_argument("--auto", action="store_true",
                    help="ゲートを全部通った在庫を1件だけ自動投稿する（schedule 用）")
    ap.add_argument("--stock-id", default="",
                    help="投稿する在庫を名指しする（手動テスト用）。"
                         "省略すると最古の approved を自動で選ぶ（定期運用用）")
    ap.add_argument("--mark-posted", default="")
    ap.add_argument("--posted-id", default="")
    ap.add_argument("--posted-url", default="", help="親投稿のURL")
    ap.add_argument("--reply-url", default="", help="返信（2投稿目）のURL")
    a = ap.parse_args()
    spec = ss.load_spec()

    # ★緊急停止。このファイルがあれば、何があっても投稿しない。
    #   人が1ファイル置くだけで全自動投稿を止められるようにしておく。
    stop = ROOT / "workspace" / "social" / "EMERGENCY_STOP"
    if stop.exists() and (a.approve or a.auto):
        print(f"EMERGENCY_STOP があるので投稿しない: {stop}")
        print(stop.read_text(encoding="utf-8")[:300] if stop.stat().st_size else "")
        return

    if a.mark_posted:
        if not (a.posted_id or a.posted_url):
            print("--posted-id か --posted-url のどちらかが要る")
            sys.exit(1)
        mark_posted(spec, a.mark_posted, a.posted_id, a.posted_url,
                    a.reply_url)
        return

    if a.platform == "threads":
        # **投稿はしない（トークンが無い）。** 貼るものをそのまま出す。
        # ここに出た文字列を、そのままコピーして貼る。
        # ラベル（【1投稿目】など）は付けない。付けると本文の一部として出る
        if not a.stock_id:
            print("Threads は投稿用トークンが無い。手で貼ってから "
                  "--mark-posted で登録する。\n"
                  "貼る本文を出すには --stock-id を渡す。")
            sys.exit(1)
        s, why = pick_by_id(spec, "threads", a.stock_id)
        if why:
            print(f"出せない: {why}")
            sys.exit(1)
        for i, part in enumerate(s["thread_parts"], 1):
            where = "新規投稿" if i == 1 else f"{i - 1}投稿目への返信"
            urls = sg.URL.findall(part)
            print(f"───── {i}／{len(s['thread_parts'])}（{where}）"
                  f" {len(part)}字 URL{len(urls)}個 ─────")
            print(part)
        print("──────────────────────────────────────────────")
        print(f"stock_id: {s['stock_id']} / state: {s['state']}")
        print("貼り終わったら、親投稿と返信のURLを渡して記録する:\n"
              f"  python social_post.py --mark-posted {s['stock_id']} \\\n"
              f"      --posted-url <親投稿のURL> --reply-url <返信のURL>")
        return

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
    will_post = a.approve or a.auto
    art = gen.fetch_article(s["article_id"]) if will_post else None
    if will_post:
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

    if not will_post:
        print("\n--approve も --auto も無いので、ここで終わり。**投稿していない。**")
        return
    if a.auto and not a.approve:
        # ★ここまで来たということは、投稿直前のゲートを全部通っている。
        #   人の承認の代わりに、機械承認で1件だけ出す。
        print("\n[auto] 投稿直前のゲートを全て通過。機械承認で1件だけ投稿する。")

    # ── 送る直前の表示と、その本文の固定 ─────────────────
    shown_hash = show_before_post(s, a.platform, spec)
    sent_text = s["text"]

    # 送る本文のURLが実際に開けるか（utm を足したあとの取り違えを見る）
    ok, lines = check_url_live(sent_text)
    print("URLの応答:\n" + lines)
    if not ok:
        print("\n投稿しない: URLが200で返らない")
        sys.exit(1)

    # Xの数え方で上限を超えていないか（送る本文そのもので数え直す）
    if a.platform == "x":
        w = sg.weighted_len(spec, sent_text)
        lim = spec["x"]["weighted"]["hard_limit"]
        print(f"X加重: {w} / {lim}")
        if w > lim:
            print(f"\n投稿しない: X加重が上限を超えている（{w} > {lim}）")
            sys.exit(1)

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
