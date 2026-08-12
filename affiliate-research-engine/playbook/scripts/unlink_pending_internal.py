#!/usr/bin/env python3
"""
unlink_pending_internal.py
公開中の記事から「まだ公開されていない記事へのリンク」を外す。

★2026-08-12。#999 の本文に `?p=1001` へのリンクがあり、#1001 が未公開のため 404 だった。
  #1001 を前倒し公開はしない。**リンクだけ外して文言は残す**（非リンク表記にする）。
  #1001 が公開されたら、内部リンクエンジンの次回監査で再追加候補にする。

★アンカー1つだけを text へ置き換える。それ以外の本文は1文字も変えない。
  置換前後で「他の href が全て一致すること」を検証してから PUT する。
  一致しなければ何もせず異常終了する。

  POST_ID=999 TARGET=?p=1001 DRY_RUN=true python unlink_pending_internal.py
"""
import os
import re
import sys

import requests

SITE = "https://sakura-eigo.com"
WP = f"{SITE}/wp-json/wp/v2"
AUTH = ("rei.00pt2342@gmail.com", os.environ.get("WP_APP_PASSWORD", ""))

POST_ID = int(os.environ.get("POST_ID", "999"))
TARGET = os.environ.get("TARGET", "?p=1001")
DRY_RUN = (os.environ.get("DRY_RUN", "true").lower() != "false")

_HREF = re.compile(r'href\s*=\s*["\']([^"\']+)["\']', re.I)
_TAG = re.compile(r"<[^>]+>")


def main():
    r = requests.get(f"{WP}/posts/{POST_ID}", auth=AUTH, params={"context": "edit"},
                     timeout=30)
    if r.status_code >= 400:
        print(f"[unlink] #{POST_ID} を取得できません HTTP {r.status_code}")
        sys.exit(1)
    j = r.json()
    before = j["content"]["raw"]

    pat = re.compile(r'<a\b[^>]*href="[^"]*' + re.escape(TARGET)
                     + r'[^"]*"[^>]*>(.*?)</a>', re.S | re.I)
    hits = pat.findall(before)
    if not hits:
        print(f"[unlink] #{POST_ID} に {TARGET} へのリンクはありません。何もしません")
        return
    if len(hits) != 1:
        print(f"[unlink] {TARGET} へのリンクが {len(hits)} 本あります。"
              "1本だけを想定しているので中止します")
        sys.exit(1)

    inner = _TAG.sub("", hits[0]).strip()
    after = pat.sub(lambda m: _TAG.sub("", m.group(1)).strip(), before, count=1)

    # ★検証：消えた href はターゲット1本だけで、他は完全一致すること
    hb, ha = _HREF.findall(before), _HREF.findall(after)
    removed = [h for h in hb if h not in ha or hb.count(h) != ha.count(h)]
    kept_ok = [h for h in hb if TARGET not in h] == ha
    print(f"[unlink] #{POST_ID}")
    print(f"  リンク文言   : 「{inner}」")
    print(f"  外した href  : {removed}")
    print(f"  href 本数    : {len(hb)} → {len(ha)}")
    print(f"  他href完全一致: {kept_ok}")
    print(f"  本文長       : {len(before)} → {len(after)}（差 {len(before)-len(after)}）")

    if not kept_ok or len(removed) != 1 or TARGET not in removed[0]:
        print("[unlink] ★想定外の差分。PUTせずに中止します")
        sys.exit(1)
    if inner not in after:
        print("[unlink] ★文言が本文から消えました。PUTせずに中止します")
        sys.exit(1)

    if DRY_RUN:
        print("[unlink] DRY_RUN のため PUT しません")
        return

    p = requests.post(f"{WP}/posts/{POST_ID}", auth=AUTH, timeout=30,
                      json={"content": after})
    if p.status_code >= 400:
        print(f"[unlink] 更新に失敗 HTTP {p.status_code}: {p.text[:200]}")
        sys.exit(1)
    print(f"[unlink] 更新しました。status={p.json().get('status')} "
          f"modified={p.json().get('modified')}")

    # ★事後確認：もう404リンクが無いこと
    v = requests.get(f"{WP}/posts/{POST_ID}", auth=AUTH,
                     params={"context": "edit"}, timeout=30).json()
    print(f"[unlink] 事後確認 {TARGET} の残存: {v['content']['raw'].count(TARGET)}件")


if __name__ == "__main__":
    main()
