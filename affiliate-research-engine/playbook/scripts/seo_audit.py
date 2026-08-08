#!/usr/bin/env python3
"""
seo_audit.py
サイト全体の技術的な問題を洗い出す。**設定は変えない。読むだけ。**

直近90日で表示0・47本中28本が未認識という状態は、
記事の中身より前の問題である可能性が高い。
インデックスされない原因を先に潰すほうが、記事を増やすより効く。

見るもの:
  検索エンジン表示設定 / robots.txt / XMLサイトマップ / サイトマップ内URL /
  meta robots / X-Robots-Tag / canonical / HTTPステータス / リダイレクト /
  www・HTTPSの統一 / 重複URL / アーカイブ / 添付ファイルページ /
  タイトル・descriptionの重複 / 内部リンク / 孤立記事 / 構造化データ

出力: workspace/seo/AUDIT.md / issues.csv
"""
import csv
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings()
sys.path.insert(0, str(Path(__file__).parent))
import quality_rules as _q
import wp_audit as _wa

JST = timezone(timedelta(hours=9))
SITE = "https://sakura-eigo.com"
WP_BASE = f"{SITE}/wp-json/wp/v2"
WP_USER = "rei.00pt2342@gmail.com"
WP_PASS = os.environ.get("WP_APP_PASSWORD", "")
OUT = Path("affiliate-research-engine/playbook/workspace/seo")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0"}

issues = []


def add(sev, title, detail, urls=0, fix=""):
    issues.append({"severity": sev, "title": title, "detail": detail,
                   "urls": urls, "suggested_fix": fix, "auto_fixed": ""})
    print(f"[{sev}] {title} … {detail[:90]}")


def get(url, **kw):
    try:
        return requests.get(url, headers=UA, timeout=45, verify=False, **kw)
    except Exception as e:
        return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    L = [f"# 技術SEO監査 {stamp}\n\n**設定は変えていない。読んだだけ。**\n\n"]

    # ── 1. WordPress の検索エンジン表示設定 ──────────────────
    s = get(f"{WP_BASE}/settings", auth=(WP_USER, WP_PASS))
    blog_public = None
    if s is not None and s.status_code == 200:
        j = s.json()
        # /settings は blog_public を返さないことがあるので両方見る
        blog_public = j.get("blog_public")
    L.append("## 1. 検索エンジン表示設定\n\n")
    if blog_public is None:
        L.append("- REST API からは取得できなかった。"
                 "**管理画面 → 設定 → 表示設定 → 検索エンジンでの表示** を目視で確認する\n")
    else:
        L.append(f"- blog_public = `{blog_public}`（0なら検索避けON）\n")
        if str(blog_public) == "0":
            add("critical", "検索避けがONになっている",
                "設定 → 表示設定 →「検索エンジンがサイトをインデックスしないようにする」",
                1, "チェックを外す")

    # ── 2. robots.txt ────────────────────────────────────
    r = get(f"{SITE}/robots.txt")
    L.append("\n## 2. robots.txt\n\n")
    if r is None or r.status_code != 200:
        add("high", "robots.txt が取得できない",
            f"HTTP {getattr(r, 'status_code', 'なし')}", 1, "出力されるようにする")
        L.append("- 取得できなかった\n")
    else:
        body = r.text
        L.append(f"```\n{body[:800]}\n```\n")
        if re.search(r"^\s*Disallow:\s*/\s*$", body, re.M):
            add("critical", "robots.txt が全ページを拒否している",
                "Disallow: / がある", 1, "この行を外す")
        sm = re.findall(r"(?im)^\s*Sitemap:\s*(\S+)", body)
        L.append(f"- 記載されたサイトマップ: {sm or '**なし**'}\n")
        if not sm:
            add("medium", "robots.txt にサイトマップの記載が無い",
                "クロールの入口が1つ減る", 1,
                "Sitemap: の行を足す（SEOプラグインの設定で出せる）")

    # ── 3. XMLサイトマップ ────────────────────────────────
    L.append("\n## 3. XMLサイトマップ\n\n")
    cands = [f"{SITE}/sitemap_index.xml", f"{SITE}/wp-sitemap.xml",
             f"{SITE}/sitemap.xml", f"{SITE}/sitemap-index.xml"]
    sm_urls, sm_found = set(), []
    for c in cands:
        rr = get(c, allow_redirects=True)
        if rr is not None and rr.status_code == 200 and "<" in rr.text[:200]:
            sm_found.append((c, rr.url, len(rr.text)))
            locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", rr.text)
            for loc in locs:
                if loc.endswith(".xml"):
                    r2 = get(loc)
                    if r2 is not None and r2.status_code == 200:
                        sm_urls |= set(re.findall(r"<loc>\s*([^<\s]+)\s*</loc>",
                                                  r2.text))
                else:
                    sm_urls.add(loc)
    for c, fin, n in sm_found:
        L.append(f"- {c} → {fin}（{n}バイト）\n")
    L.append(f"- サイトマップに載っているURL: **{len(sm_urls)}件**\n")
    if not sm_found:
        add("critical", "XMLサイトマップが見つからない",
            "sitemap_index.xml / wp-sitemap.xml / sitemap.xml のいずれも無い", 1,
            "SEOプラグインでサイトマップを出す")

    # ── 4. 公開記事とサイトマップの突き合わせ ────────────────
    posts = _wa.published()
    links = {p.get("link", "").rstrip("/") for p in posts}
    sm_norm = {u.rstrip("/") for u in sm_urls}
    missing = sorted(links - sm_norm)
    L.append(f"\n## 4. 公開記事 {len(posts)}本とサイトマップの突き合わせ\n\n")
    L.append(f"- サイトマップに**載っていない**公開記事: **{len(missing)}本**\n")
    for u in missing[:15]:
        L.append(f"  - {u}\n")
    if missing:
        add("high", "公開記事がサイトマップから漏れている",
            f"{len(missing)}本", len(missing),
            "サイトマップの対象に投稿が含まれているかを確認する")

    # ── 5. 各記事の HTTP / canonical / noindex ────────────
    L.append("\n## 5. 記事ごとの状態\n\n")
    noindex, canon_bad, http_bad = [], [], []
    titles, descs = defaultdict(list), defaultdict(list)
    sample = posts
    for p in sample:
        url = p.get("link", "")
        rr = get(url, allow_redirects=True)
        if rr is None or rr.status_code != 200:
            http_bad.append((p["id"], url, getattr(rr, "status_code", "err")))
            continue
        h = rr.text
        if re.search(r'<meta[^>]+name=["\']robots["\'][^>]+noindex', h, re.I):
            noindex.append((p["id"], url))
        if "noindex" in rr.headers.get("X-Robots-Tag", "").lower():
            noindex.append((p["id"], url + "（X-Robots-Tag）"))
        m = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)',
                      h)
        if m and m.group(1).rstrip("/") != url.rstrip("/"):
            canon_bad.append((p["id"], url, m.group(1)))
        t = re.search(r"<title[^>]*>(.*?)</title>", h, re.DOTALL | re.I)
        if t:
            titles[_q.strip_tags(t.group(1)).strip()].append(p["id"])
        d = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)',
                      h, re.I)
        if d:
            descs[d.group(1).strip()[:120]].append(p["id"])

    L.append(f"- HTTP が 200 でない記事: **{len(http_bad)}本**\n")
    for i, u, c in http_bad[:10]:
        L.append(f"  - [{i}] {c} {u}\n")
    L.append(f"- noindex が付いている記事: **{len(noindex)}本**\n")
    for i, u in noindex[:10]:
        L.append(f"  - [{i}] {u}\n")
    L.append(f"- canonical が自分以外を指す記事: **{len(canon_bad)}本**\n")
    for i, u, c in canon_bad[:10]:
        L.append(f"  - [{i}] {u} → {c}\n")
    if http_bad:
        add("high", "HTTP 200 を返さない記事がある", f"{len(http_bad)}本",
            len(http_bad), "個別に原因を見る")
    if noindex:
        add("critical", "noindex が付いた公開記事がある", f"{len(noindex)}本",
            len(noindex), "SEOプラグインの設定を確認して外す")
    if canon_bad:
        add("high", "canonical が別URLを指している", f"{len(canon_bad)}本",
            len(canon_bad), "自己参照に直す")

    dupt = {k: v for k, v in titles.items() if len(v) > 1}
    dupd = {k: v for k, v in descs.items() if len(v) > 1}
    L.append(f"\n- 重複タイトル: **{len(dupt)}組**\n")
    for k, v in list(dupt.items())[:5]:
        L.append(f"  - {k[:60]} … {v}\n")
    L.append(f"- 重複description: **{len(dupd)}組**\n")
    if dupt:
        add("medium", "タイトルが重複している記事がある", f"{len(dupt)}組",
            sum(len(v) for v in dupt.values()), "タイトルを分ける")
    if dupd:
        add("low", "descriptionが重複している", f"{len(dupd)}組",
            sum(len(v) for v in dupd.values()), "記事ごとに書く")

    # ── 6. www / HTTP の統一 ─────────────────────────────
    L.append("\n## 6. URLの統一\n\n")
    for u in (f"http://sakura-eigo.com/", f"https://www.sakura-eigo.com/",
              f"http://www.sakura-eigo.com/"):
        rr = get(u, allow_redirects=True)
        if rr is None:
            L.append(f"- {u} … 接続できない\n")
            continue
        chain = " → ".join([h.url for h in rr.history] + [rr.url])
        ok = rr.url.startswith("https://sakura-eigo.com")
        L.append(f"- {u} → {rr.status_code} {'✅' if ok else '⚠️'} {chain}\n")
        if not ok:
            add("medium", f"{u} が正規URLへ寄っていない", chain, 1,
                "301で https://sakura-eigo.com/ へ寄せる")

    # ── 7. アーカイブと添付ファイルページ ───────────────────
    L.append("\n## 7. アーカイブ・添付ファイルページ\n\n")
    for name, u in (("カテゴリ一覧", f"{SITE}/category/"),
                    ("タグ一覧", f"{SITE}/tag/"),
                    ("日付アーカイブ", f"{SITE}/2026/08/"),
                    ("著者アーカイブ", f"{SITE}/author/rei/")):
        rr = get(u, allow_redirects=True)
        code = getattr(rr, "status_code", "err")
        ni = bool(rr is not None and rr.status_code == 200 and
                  re.search(r'name=["\']robots["\'][^>]+noindex', rr.text, re.I))
        L.append(f"- {name} `{u}` … {code}"
                 f"{' / noindex' if ni else ''}\n")

    # ── 8. 内部リンクと孤立記事 ──────────────────────────
    L.append("\n## 8. 内部リンクと孤立記事\n\n")
    inbound = Counter()
    for p in posts:
        html = p.get("content", {}).get("rendered", "")
        me = p.get("link", "").rstrip("/")
        for m in re.finditer(r'href="(https://sakura-eigo\.com/[^"#?]+)', html):
            t = m.group(1).rstrip("/")
            if t != me and t in links:
                inbound[t] += 1
    orphan = [p for p in posts if inbound.get(p.get("link", "").rstrip("/"), 0) == 0]
    L.append(f"- 記事間の内部リンク: **{sum(inbound.values())}本**\n")
    L.append(f"- どこからもリンクされていない記事（孤立）: **{len(orphan)}本 / "
             f"{len(posts)}本**\n")
    if len(orphan) > len(posts) * 0.5:
        add("high", "記事の大半が内部リンクで繋がっていない",
            f"孤立 {len(orphan)}/{len(posts)}本。クロールの導線が弱い",
            len(orphan), "監査済みの記事から順に相互リンクを足す")

    # ── 9. 構造化データ ─────────────────────────────────
    L.append("\n## 9. 構造化データ\n\n")
    rr = get(posts[0].get("link", "")) if posts else None
    if rr is not None and rr.status_code == 200:
        types = re.findall(r'"@type"\s*:\s*"([^"]+)"', rr.text)
        L.append(f"- サンプル記事の @type: {sorted(set(types)) or '**なし**'}\n")
        if not types:
            add("medium", "構造化データが出ていない",
                "サンプル記事に JSON-LD が無い", len(posts),
                "SEOプラグインで Article を出す")

    # ── まとめ ──────────────────────────────────────────
    sev = Counter(i["severity"] for i in issues)
    head = ["\n---\n\n## 見つかった問題\n\n",
            f"critical {sev['critical']} / high {sev['high']} / "
            f"medium {sev['medium']} / low {sev['low']}\n\n",
            "| 重要度 | 問題 | 影響URL数 | 修正案 |\n|---|---|---|---|\n"]
    for i in issues:
        head.append(f"| {i['severity']} | {i['title']} | {i['urls']} | "
                    f"{i['suggested_fix']} |\n")
    L = L[:1] + head + L[1:]

    (OUT / "AUDIT.md").write_text("".join(L), encoding="utf-8")
    if issues:
        with open(OUT / "issues.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(issues[0].keys()))
            w.writeheader()
            w.writerows(issues)
    print(f"\n問題 {len(issues)}件 → workspace/seo/AUDIT.md")


if __name__ == "__main__":
    main()
