#!/usr/bin/env python3
"""公開済み記事の2種類の不整合だけを直す。★それ以外の本文は1文字も変えない。

  ① 未公開記事への内部リンク（404）を外す。文言は非リンクで残す
  ② アフィリリンクが0本なのに付いているPR表記を外す

★2026-08-13。#999 → #1001 と同じ連鎖が2日続けて起きたので、
  1本のスクリプトで両方直せるようにした。

★安全装置：置換前後で必ず検証し、1つでも崩れたらPUTしない。
  ・外すと決めたhref以外は完全一致（順序込み）
  ・アフィリリンクの本数が変わらない
  ・1×1計測gifの本数が変わらない
  ・タイトル・スラッグ・アイキャッチ・カテゴリを触らない
  ・本文が想定より縮んでいない

  POST_ID=1001 DRY_RUN=true python fix_published_article.py
"""
import os
import re
import sys

import requests

SITE = "https://sakura-eigo.com"
WP = f"{SITE}/wp-json/wp/v2"
AUTH = ("rei.00pt2342@gmail.com", os.environ.get("WP_APP_PASSWORD", ""))

POST_ID = int(os.environ.get("POST_ID", "0"))
DRY_RUN = (os.environ.get("DRY_RUN", "true").lower() != "false")

_HREF = re.compile(r'href\s*=\s*["\']([^"\']+)["\']', re.I)
_TAG = re.compile(r"<[^>]+>")
_ASP = re.compile(r"px\.a8\.net|af\.moshimo\.com|a8\.net|moshimo", re.I)
_GIF = re.compile(r"<img[^>]*a8\.net[^>]*>", re.I)
# 内部リンクのうち ?p=数字 の形。固定URLになる前の記事を指している
_INTERNAL_P = re.compile(r'<a\b[^>]*href="(https?://[^"]*\?p=(\d+))"[^>]*>(.*?)</a>', re.S | re.I)
# PR表記のブロック。★段落ごと外す。文中に混ざっている場合は触らない（誤爆防止）
_PR_BLOCK = re.compile(
    r"<p[^>]*>\s*(?:※\s*)?[^<]{0,40}"
    r"(?:アフィリエイトリンクが含まれま[^<]{0,20}|PRを含みま[^<]{0,10}|広告を含みま[^<]{0,10})"
    r"[^<]{0,20}</p>\s*", re.I)


def http_status(url):
    try:
        r = requests.head(url, timeout=15, allow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0 fixer"})
        if r.status_code >= 400:
            r = requests.get(url, timeout=20, allow_redirects=True, stream=True,
                             headers={"User-Agent": "Mozilla/5.0 fixer"})
        return r.status_code
    except Exception:
        return None


def main():
    if not POST_ID:
        print("POST_ID が要ります")
        sys.exit(1)
    r = requests.get(f"{WP}/posts/{POST_ID}", auth=AUTH, params={"context": "edit"},
                     timeout=30)
    if r.status_code >= 400:
        print(f"#{POST_ID} を取得できません HTTP {r.status_code}")
        sys.exit(1)
    j = r.json()
    before = j["content"]["raw"]
    after = before
    actions = []

    # ── ① 404 になっている内部リンクを外す
    dead = []
    for m in _INTERNAL_P.finditer(before):
        url, pid, inner = m.group(1), m.group(2), m.group(3)
        code = http_status(url)
        if code is None or code >= 400:
            dead.append((m.group(0), url, pid, _TAG.sub("", inner).strip(), code))

    for whole, url, pid, text, code in dead:
        after = after.replace(whole, text, 1)
        actions.append(f"未公開記事へのリンクを外した: ?p={pid} ({code}) 文言「{text}」は残した")

    # ── ② アフィリリンク0本なのにPR表記がある
    aff_before = len(_ASP.findall(before))
    if aff_before == 0:
        m = _PR_BLOCK.search(after)
        if m:
            after = after.replace(m.group(0), "", 1)
            actions.append("アフィリリンク0本なのでPR表記の段落を外した: "
                           + _TAG.sub("", m.group(0)).strip()[:60])

    if not actions:
        print(f"#{POST_ID}: 直すところがありません")
        return

    # ── 検証
    hb, ha = _HREF.findall(before), _HREF.findall(after)
    removed_urls = {u for _, u, _, _, _ in dead}
    expect = [h for h in hb if h not in removed_urls]
    problems = []
    if expect != ha:
        problems.append(f"href が想定と違う（{len(hb)}→{len(ha)}、期待{len(expect)}）")
    if len(_ASP.findall(after)) != aff_before:
        problems.append("アフィリリンクの本数が変わった")
    if len(_GIF.findall(after)) != len(_GIF.findall(before)):
        problems.append("1×1計測gifの本数が変わった")
    for _, _, _, text, _ in dead:
        if text and text not in after:
            problems.append(f"文言が消えた: {text[:30]}")
    shrink = len(before) - len(after)
    if shrink > 400:
        problems.append(f"本文が{shrink}文字も縮んだ（想定外）")

    print(f"#{POST_ID} {j['title'].get('raw') or j['title'].get('rendered','')}")
    for a in actions:
        print(f"  ・{a}")
    print(f"  href {len(hb)} → {len(ha)} / アフィリ {aff_before}本維持 / "
          f"gif {len(_GIF.findall(before))}本維持 / 本文 {len(before)}→{len(after)}")

    if problems:
        print("★想定外の差分。PUTせずに中止します:")
        for p in problems:
            print(f"    - {p}")
        sys.exit(1)
    if DRY_RUN:
        print("  DRY_RUN のため PUT しません")
        return

    # ★content だけ送る。タイトル・スラッグ・アイキャッチ・カテゴリは触らない
    p = requests.post(f"{WP}/posts/{POST_ID}", auth=AUTH, timeout=30,
                      json={"content": after})
    if p.status_code >= 400:
        print(f"  更新に失敗 HTTP {p.status_code}: {p.text[:200]}")
        sys.exit(1)
    d = p.json()
    print(f"  更新しました status={d.get('status')} modified={d.get('modified')}")

    v = requests.get(f"{WP}/posts/{POST_ID}", auth=AUTH, params={"context": "edit"},
                     timeout=30).json()["content"]["raw"]
    print(f"  事後確認: 404リンク残存 {sum(1 for _,u,_,_,_ in dead if u in v)}件 / "
          f"PR表記 {'あり' if _PR_BLOCK.search(v) else 'なし'} / "
          f"アフィリ {len(_ASP.findall(v))}本")


if __name__ == "__main__":
    main()
