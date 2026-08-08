#!/usr/bin/env python3
"""
link_checker.py
アフィリエイトリンクが、記事で説明しているサービスに実際に飛ぶかを確かめる。

記事は「録音を送ると発音のズレを返してくれる」と書いているのに、
リンク先が別サービスだったら、体験表現以前の問題になる。
speek（発音矯正）と Speak（AI英会話アプリ）は名前が1文字違いで、別物。

**ASPの管理画面には入らない。** 公開されているリンクをたどるだけ。
1本につき1回しかアクセスしない（本人クリックを増やさないため）。
定期実行しない。workflow_dispatch でだけ動かす。

出力:
  workspace/claims/LINK_AUDIT.md
  workspace/claims/LINK_AUDIT.csv
"""
import csv
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from html import unescape as html_unescape
from urllib.parse import unquote

import requests
import urllib3

urllib3.disable_warnings()
sys.path.insert(0, str(Path(__file__).parent))
import quality_rules as _q
import wp_audit as _wa

OUT = Path("affiliate-research-engine/playbook/workspace/claims")
JST = timezone(timedelta(hours=9))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# 確かめたいサービス。空なら全部
ONLY = [s for s in os.environ.get("ONLY", "").split(",") if s.strip()]
# 対象記事。空なら全部
POSTS = [s for s in os.environ.get("POSTS", "").split(",") if s.strip()]

A_RE = re.compile(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL | re.I)

# 運営者を名乗っている箇所。会社名は推測せず、書いてある行をそのまま拾う
COMPANY_RE = re.compile(
    r"(運営会社|運営元|会社名|商号|販売業者|提供元|Company)\s*[:：]?\s*"
    r"([^<>\n\r\t]{2,60})")


def links():
    """公開記事から、アフィリエイトリンクを (URL, 文言, 記事ID) で集める。"""
    found = {}
    for p in _wa.published():
        pid = str(p["id"])
        if POSTS and pid not in POSTS:
            continue
        html = p.get("content", {}).get("rendered", "")
        for m in A_RE.finditer(html):
            url, inner = m.group(1), _q.strip_tags(m.group(2))
            if not _q.AFFILIATE_LINK_RE.search(url):
                continue
            if ONLY and not any(s.lower() in inner.lower() for s in ONLY):
                continue
            d = found.setdefault(url, {"url": url, "anchors": set(), "posts": set()})
            d["anchors"].add(inner.strip()[:60])
            d["posts"].add(pid)
    return list(found.values())


def title_of(html):
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.I)
    return re.sub(r"\s+", " ", _q.strip_tags(m.group(1))).strip() if m else ""


def meta_of(html, prop):
    m = re.search(rf'<meta[^>]+(?:property|name)="{prop}"[^>]+content="([^"]*)"',
                  html, re.I) or \
        re.search(rf'<meta[^>]+content="([^"]*)"[^>]+(?:property|name)="{prop}"',
                  html, re.I)
    return m.group(1).strip() if m else ""


def destination(url):
    """アフィリンクの中に書いてある遷移先を、**踏まずに**取り出す。

    もしもの click URL は `url=` に遷移先をそのまま持っている。
    ここから読めば、ASPに本人クリックを1件も計上せずに確かめられる
    （2026-08-08に判明。それまでは踏むしかないと思っていた）。
    A8 のように遷移先を持たない形式のときは None を返す。
    """
    u = html_unescape(url)
    m = re.search(r"[?&]url=([^&]+)", u)
    if m:
        return unquote(m.group(1)), "リンクのurlパラメータから取得（踏んでいない）"
    return None, ""


def normalize(url):
    """`//host/...` のようなスキーム無しURLを直す。"""
    u = html_unescape(url).strip()
    if u.startswith("//"):
        u = "https:" + u
    return u


def follow(url):
    """遷移先を確かめる。**アフィリンクは踏まない。**

    遷移先がリンクの中に書いてあるなら、そこへ直接アクセスする。
    書いていない形式のときだけ、アフィリンクをたどる（1回だけ）。
    """
    dest, how = destination(url)
    target, note = (dest, how) if dest else (normalize(url), "遷移先が書かれていないのでアフィリンクをたどった")
    s = requests.Session()
    try:
        r = s.get(target, headers={"User-Agent": UA}, allow_redirects=True,
                  timeout=45, verify=False)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}", "declared_dest": dest or "",
                "how": note}
    chain = [h.url for h in r.history] + [r.url]
    html = r.text if "text/html" in r.headers.get("Content-Type", "") else ""
    comp = COMPANY_RE.search(_q.strip_tags(html)) if html else None
    return {
        "declared_dest": dest or "",
        "how": note,
        "status": r.status_code,
        "final_url": r.url,
        "domain": re.sub(r"^www\.", "", (re.match(r"https?://([^/]+)", r.url)
                                         or re.match("()", "")).group(1) or ""),
        "hops": len(chain) - 1,
        "chain": " → ".join(chain),
        "title": title_of(html),
        "og_site_name": meta_of(html, "og:site_name"),
        "og_title": meta_of(html, "og:title"),
        "description": meta_of(html, "description")[:200],
        "company_line": (comp.group(0).strip()[:120] if comp else ""),
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ls = links()
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    print(f"対象リンク {len(ls)}本 / {stamp}")
    if not ls:
        print("該当なし。ONLY / POSTS の指定を見直す")
        return

    rows = []
    for d in sorted(ls, key=lambda x: sorted(x["posts"])):
        print(f"\n→ {' / '.join(sorted(d['anchors']))}")
        print(f"   記事 {' '.join(sorted(d['posts']))}")
        r = follow(d["url"])
        rows.append({
            "checked_at": stamp,
            "posts": " ".join(sorted(d["posts"])),
            "anchor": " / ".join(sorted(d["anchors"])),
            "affiliate_url": d["url"],
            **{k: r.get(k, "") for k in
               ("declared_dest", "how", "status", "final_url", "domain",
                "hops", "chain", "title", "og_site_name", "og_title",
                "description", "company_line", "error")},
        })
        for k in ("declared_dest", "how", "status", "final_url", "domain",
                  "title", "og_site_name", "company_line", "error"):
            if r.get(k):
                print(f"   {k}: {r[k]}")

    with open(OUT / "LINK_AUDIT.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    L = [f"# アフィリンクの遷移先 {stamp}\n\n",
         "記事の説明と、リンクが実際に飛ぶ先が一致しているかを見るための記録。\n"
         "**ASPの管理画面には入っていない。**\n"
         "もしものリンクは `url=` に遷移先が書いてあるので、**踏まずに**そこへ直接見に行く。\n"
         "本人クリックは1件も計上していない。\n\n",
         "判定は書いていない。**取得した事実だけ**を並べる。\n\n"]
    for r in rows:
        L.append(f"---\n\n## {r['anchor']}\n\n")
        L.append(f"- 記事: {r['posts']}\n")
        L.append(f"- 取得日時: {r['checked_at']}\n")
        L.append(f"- アフィリエイトURL: `{r['affiliate_url']}`\n")
        if r.get("declared_dest"):
            L.append(f"- **リンクに書かれた遷移先**: {r['declared_dest']}\n")
        L.append(f"- 取得のしかた: {r.get('how','')}\n")
        if r.get("error"):
            L.append(f"- **たどれなかった**: {r['error']}\n\n")
            continue
        L.append(f"- HTTP: {r['status']} / リダイレクト {r['hops']}回\n")
        L.append(f"- **最終URL**: {r['final_url']}\n")
        L.append(f"- **ドメイン**: `{r['domain']}`\n")
        L.append(f"- **ページタイトル**: {r['title'] or '（取れず）'}\n")
        L.append(f"- og:site_name: {r['og_site_name'] or '（なし）'}\n")
        L.append(f"- og:title: {r['og_title'] or '（なし）'}\n")
        L.append(f"- description: {r['description'] or '（なし）'}\n")
        L.append(f"- 運営会社の記載: {r['company_line'] or '（このページには無い）'}\n")
        L.append(f"- 遷移: {r['chain']}\n\n")
    (OUT / "LINK_AUDIT.md").write_text("".join(L), encoding="utf-8")
    print(f"\n{len(rows)}本 → LINK_AUDIT.md")


if __name__ == "__main__":
    main()
