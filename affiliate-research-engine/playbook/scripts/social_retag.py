#!/usr/bin/env python3
"""
social_retag.py
承認済み在庫の**リンクの計測パラメータだけ**を差し替える。

  python social_retag.py --stock-id X-546-b \
      --url "https://sakura-eigo.com/...?utm_source=x&utm_medium=social&..."

`utm_source` だけだと、同じ媒体・同じ記事の別投稿を後から区別できない。
`utm_content` に在庫IDまで入れておくと、どの在庫から来たかを追える。

**本文は1文字も変えない。** 変えてよいのは、末尾のURLの `?` から後ろだけ。
変わったのがそこだけであることを、この場で照合してから保存する。

  - 記事URL（`?` の前）が違えば止まる
  - URL以外の文字が1文字でも変われば止まる
  - 承認済み以外は触らない。状態は approved のまま動かさない
  - 名指しした1件しか書かない

`content_hash` は本文が変わるので取り直す。**取り直した事実を履歴に残す**
（旧ハッシュ・旧URL・理由）。残さないと、承認したものと違う文が
いつのまにか出ていく。
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
import social_spec as ss
import social_gate as sg
import social_inventory as inv


def retag(spec, stock, new_url, reason):
    """URLのクエリだけ差し替えた在庫を返す。戻り値は (在庫, 止める理由)。"""
    # 承認済みと承認待ちだけ。**投稿済み・退役・却下には触らない**
    # （投稿済みのURLを書き換えると、出したものと記録が食い違う）
    if stock["state"] not in ("approved", "awaiting_approval"):
        return None, (f"{stock['stock_id']} は {stock['state']}。"
                      f"approved / awaiting_approval 以外は触らない")
    olds = sg.URL.findall("\n".join(stock["thread_parts"]))
    if len(olds) != 1:
        return None, f"URLが{len(olds)}個ある。1個でないと差し替えない"
    old = olds[0]
    if old.split("?")[0].rstrip("/") != new_url.split("?")[0].rstrip("/"):
        return None, (f"記事URLが違う\n  旧 {old.split('?')[0]}"
                      f"\n  新 {new_url.split('?')[0]}")
    utm = spec[stock["platform"]]["url"]["utm"]
    if utm not in new_url:
        return None, f"{utm} が無い: {new_url}"

    parts = [p.replace(old, new_url) for p in stock["thread_parts"]]
    # **URL以外が変わっていないことを、URLを伏せて突き合わせる**
    def mask(ps):
        return [sg.URL.sub("<URL>", p) for p in ps]
    if mask(parts) != mask(stock["thread_parts"]):
        return None, "URL以外の文字が変わっている"

    stock["prior_links"] = (stock.get("prior_links") or []) + [{
        "at": inv.now(), "old_url": old, "new_url": new_url,
        "old_content_hash": stock["content_hash"], "reason": reason}]
    stock["thread_parts"] = parts
    stock["text"] = "\n\n".join(parts)
    stock["content_hash"] = inv.content_hash(parts)
    stock.setdefault("history", []).append(
        {"at": inv.now(), "state": stock["state"], "note": f"URL差し替え: {reason}"})
    return stock, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stock-id", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--reason", default="計測パラメータの追加")
    ap.add_argument("--write", action="store_true",
                    help="付けないと差分を見せるだけで保存しない")
    a = ap.parse_args()
    spec = ss.load_spec()

    hit = [s for _, s in inv.all_stock(spec) if s["stock_id"] == a.stock_id]
    if len(hit) != 1:
        print(f"止める: stock_id が {len(hit)}件: {a.stock_id}")
        sys.exit(1)
    s = hit[0]
    before = s["content_hash"]
    out, why = retag(spec, s, a.url, a.reason)
    if why:
        print(f"止める: {why}")
        sys.exit(1)
    print(f"{a.stock_id}: content_hash {before} → {out['content_hash']}")
    print(f"state: {out['state']}（変えない）")
    print("── 差し替え後の本文 ──")
    print(out["text"])
    if not a.write:
        print("\n--write が無いので保存していない。")
        return
    inv.save(spec, out)
    print("\n保存した。")


if __name__ == "__main__":
    main()
