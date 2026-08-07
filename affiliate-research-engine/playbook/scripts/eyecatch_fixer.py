#!/usr/bin/env python3
"""
eyecatch_fixer.py
アイキャッチのファイル名が日本語のものを、半角英数へ入れ替える。

日本語ファイル名だと Threads/Facebook のプレビュー画像が出ない。
Metaのクローラーが、エンコードされていない日本語URLを取りに行けないため。
画像自体は200で返るので、外形からは気づけない
（2026-08-07に「ChatGPT-Image-2026年8月7日-11_04_03.png」で発生）。

WordPressのAPIではファイル名を変更できない（source_url はアップロード時に固定）。
そのため「取得 → 記事スラッグの名前で再アップロード → アイキャッチを差し替え」で直す。

**古いメディアは消さない。** 本文中にその画像を直接貼っている記事があると、
消した瞬間にそちらが壊れる。容量は後から手で片づけられるが、壊れた記事は気づけない。
"""
import os
import re
import sys
from datetime import date
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings()

WP_BASE = "https://sakura-eigo.com/wp-json/wp/v2"
WP_USER = "rei.00pt2342@gmail.com"
WP_PASS = os.environ.get("WP_APP_PASSWORD", "")
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"
LIMIT = int(os.environ.get("LIMIT", "50"))
OUT = Path("affiliate-research-engine/playbook/workspace/site")

AUTH = (WP_USER, WP_PASS)
UA = {"User-Agent": "Mozilla/5.0"}


def all_posts():
    """公開・下書きを問わず、アイキャッチのある記事を集める。"""
    posts, page = [], 1
    while True:
        r = requests.get(f"{WP_BASE}/posts", auth=AUTH,
                         params={"per_page": 100, "page": page, "status": "publish,draft",
                                 "_fields": "id,title,slug,featured_media,status"},
                         headers=UA, verify=False, timeout=40)
        if r.status_code != 200:
            break
        b = r.json()
        if not b:
            break
        posts += b
        if len(b) < 100:
            break
        page += 1
    return [p for p in posts if p.get("featured_media")]


def media(mid):
    r = requests.get(f"{WP_BASE}/media/{mid}", auth=AUTH,
                     params={"_fields": "id,source_url,mime_type,alt_text"},
                     headers=UA, verify=False, timeout=40)
    return r.json() if r.status_code == 200 else None


def new_name(slug, url, post_id):
    """記事スラッグからファイル名を作る。拡張子は元のものを残す。

    スラッグ自体が日本語のことがある。その場合はURLエンコードされた
    「%e3%80%8c…」が来るので、そのまま変換すると
    「e3-80-8c-e3-83-af-…」という読めない名前になる。
    英字が実質含まれないなら、記事IDで代用する。
    """
    from urllib.parse import unquote
    ext = os.path.splitext(url.split("?")[0])[1].lower() or ".png"
    base = re.sub(r"[^a-z0-9\-]+", "-", unquote(slug or "").lower()).strip("-")[:60]
    # 英字が3文字未満なら、スラッグが日本語だったと判断する
    if len(re.findall(r"[a-z]", base)) < 3:
        base = f"eyecatch-{post_id}"
    return f"{base}{ext}"


def reupload(url, filename, mime, alt):
    """画像を取得して、新しい名前でアップロードし直す。新しいIDを返す。"""
    g = requests.get(url, headers=UA, verify=False, timeout=60)
    if g.status_code != 200 or not g.content:
        return None, f"元画像を取得できない HTTP {g.status_code}"
    r = requests.post(
        f"{WP_BASE}/media", auth=AUTH,
        headers={**UA,
                 "Content-Type": mime or "image/png",
                 "Content-Disposition": f'attachment; filename="{filename}"'},
        data=g.content, verify=False, timeout=120)
    if r.status_code not in (200, 201):
        return None, f"アップロードできない HTTP {r.status_code}: {r.text[:120]}"
    mid = r.json().get("id")
    if alt:
        requests.post(f"{WP_BASE}/media/{mid}", auth=AUTH,
                      json={"alt_text": alt}, headers=UA, verify=False, timeout=40)
    return mid, None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    posts = all_posts()
    targets = []
    for p in posts:
        m = media(p["featured_media"])
        if not m:
            continue
        url = m.get("source_url", "")
        # URLに半角英数以外が入っているものだけが対象
        if url and not url.isascii():
            targets.append((p, m))

    print(f"アイキャッチあり {len(posts)}本 / 日本語ファイル名 {len(targets)}本")

    L = [f"# アイキャッチのファイル名を直す {date.today().isoformat()}\n\n",
         f"モード: {'DRY RUN' if DRY_RUN else 'LIVE'}\n\n",
         f"対象 {len(targets)}本（今回 {min(LIMIT, len(targets))}本）\n\n",
         "| ID | 状態 | 旧ファイル名 | 新ファイル名 | 結果 |\n|---|---|---|---|---|\n"]

    ok = ng = 0
    for p, m in targets[:LIMIT]:
        old = m["source_url"].split("/")[-1]
        name = new_name(p.get("slug"), m["source_url"], p["id"])
        if DRY_RUN:
            L.append(f"| {p['id']} | {p['status']} | {old[:34]} | {name} | 未実行 |\n")
            print(f"[{p['id']}] {old[:40]} → {name}")
            ok += 1
            continue

        mid, err = reupload(m["source_url"], name,
                            m.get("mime_type"), m.get("alt_text"))
        if err:
            L.append(f"| {p['id']} | {p['status']} | {old[:34]} | {name} | {err} |\n")
            print(f"[{p['id']}] 失敗: {err}")
            ng += 1
            continue

        u = requests.post(f"{WP_BASE}/posts/{p['id']}", auth=AUTH,
                          json={"featured_media": mid}, headers=UA,
                          verify=False, timeout=40)
        if u.status_code in (200, 201):
            L.append(f"| {p['id']} | {p['status']} | {old[:34]} | {name} | 差し替え |\n")
            print(f"[{p['id']}] 差し替えた → media {mid}")
            ok += 1
        else:
            L.append(f"| {p['id']} | {p['status']} | {old[:34]} | {name} | "
                     f"記事の更新に失敗 HTTP {u.status_code} |\n")
            ng += 1

    L.append(f"\n成功 {ok} / 失敗 {ng}\n\n"
             "古いメディアは消していない。本文に直接貼っている記事があると壊れるため。\n"
             "容量が気になる場合だけ、あとから手で片づける。\n\n"
             "差し替えたあとは、Metaのシェアデバッガでキャッシュを更新すること。\n"
             "https://developers.facebook.com/tools/debug/\n")
    (OUT / "EYECATCH.md").write_text("".join(L), encoding="utf-8")
    print(f"\n成功 {ok} / 失敗 {ng}")


if __name__ == "__main__":
    main()
