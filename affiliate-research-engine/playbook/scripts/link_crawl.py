#!/usr/bin/env python3
"""
link_crawl.py
サイト全体をクロールして、内部リンクの状態を検証する。

見るもの:
  内部リンク総数 / 孤立記事 / 被リンク0 / 発リンク0 / リンク切れ /
  リダイレクト経由のリンク / 非公開記事へのリンク /
  1記事あたりの発リンク・被リンク / ハブ / カニバリ候補 /
  トップと /articles/ から主要ハブへの到達段数

  python link_crawl.py
出力: workspace/seo/LINK_CRAWL.md / .csv
"""
import csv
import os
import re
import sys
from collections import Counter, defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, unquote

import requests
import urllib3

urllib3.disable_warnings()
sys.path.insert(0, str(Path(__file__).parent))
import quality_rules as _q
import wp_audit as _wa

OUT = Path("affiliate-research-engine/playbook/workspace/seo")
JST = timezone(timedelta(hours=9))
SITE = "https://sakura-eigo.com"
UA = {"User-Agent": "Mozilla/5.0"}

SKIP = re.compile(
    r"/wp-(?:admin|content|json|includes)/|/feed/?$|\.(?:png|jpe?g|gif|svg|"
    r"css|js|ico|webp|pdf)$|^mailto:|^tel:|#", re.I)


def norm(u):
    """URLを比較できる形にそろえる。"""
    u = urlsplit(u)
    return f"{u.scheme}://{u.netloc}{u.path.rstrip('/')}/".lower()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")

    posts = _wa.published()
    pub = {norm(p["link"]): str(p["id"]) for p in posts}
    title = {str(p["id"]): re.sub(r"<[^>]+>", "", p["title"]["rendered"])
             for p in posts}
    print(f"公開記事 {len(pub)}本")

    # 記事＋トップ＋一覧をクロールする
    seeds = [f"{SITE}/", f"{SITE}/articles/"] + [p["link"] for p in posts]
    pages, out_links, status = {}, defaultdict(list), {}
    theme_counts = {}
    for u in seeds:
        try:
            r = requests.get(u, headers=UA, verify=False, timeout=45,
                             allow_redirects=True)
            status[norm(u)] = (r.status_code, norm(r.url) != norm(u), r.url)
            pages[norm(u)] = r.text if r.status_code == 200 else ""
        except Exception as e:
            status[norm(u)] = (f"ERR:{type(e).__name__}", False, "")
            pages[norm(u)] = ""
        print(f"  {u} → {status[norm(u)][0]}")

    # 本文の内部リンクを集める。
    # **テーマが自動で出す関連記事カードは本文のリンクではない。**
    # article の中にあるので、そこだけ先に落とす（2026-08-09に分けた）。
    THEME_BLOCK = re.compile(
        r'<(div|aside|nav|section|ul)[^>]*class="[^"]*'
        r'(?:related|carditem|entry-card|navi|breadcrumb|widget|pager|'
        r'sns-|toc|ez-toc)[^"]*"[^>]*>.*?</\1>',
        re.DOTALL | re.I)
    for src, html in pages.items():
        body = html
        m = re.search(r'<(?:article|main)[^>]*>(.*)</(?:article|main)>',
                      html, re.DOTALL | re.I)
        if m:
            body = m.group(1)
        theme_n = len(THEME_BLOCK.findall(body))
        body = THEME_BLOCK.sub(" ", body)
        theme_counts[norm(src)] = theme_n
        for a in re.finditer(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                             body, re.DOTALL | re.I):
            href, anchor = a.group(1), _q.strip_tags(a.group(2)).strip()
            if href.startswith("#") or SKIP.search(href):
                continue
            full = urljoin(src, href)
            if SITE not in full:
                continue
            n = norm(full)
            if n == src:
                continue
            out_links[src].append((n, anchor))

    # 記事間のリンクだけを数える
    edges, bad_anchor, broken, redirected, to_unpub = [], [], [], [], []
    for src, lst in out_links.items():
        sid = pub.get(src)
        seen = set()
        for dst, anchor in lst:
            did = pub.get(dst)
            if not did:
                # 公開記事ではない先。固定ページかもしれない
                if dst not in status:
                    try:
                        r = requests.get(dst, headers=UA, verify=False,
                                         timeout=40, allow_redirects=True)
                        status[dst] = (r.status_code, norm(r.url) != dst, r.url)
                    except Exception as e:
                        status[dst] = (f"ERR:{type(e).__name__}", False, "")
                code, red, final = status[dst]
                if code == 404:
                    broken.append((sid or src, dst, anchor))
                elif isinstance(code, str):
                    broken.append((sid or src, dst, anchor))
                elif red:
                    redirected.append((sid or src, dst, final))
                continue
            if sid and did and (sid, did) not in seen:
                seen.add((sid, did))
                edges.append((sid, did, anchor))
                if re.fullmatch(r"(?:こちら|詳しく|こちらの記事|続きを読む|"
                                r"詳細|リンク|ここ)", anchor):
                    bad_anchor.append((sid, did, anchor))

    outc = Counter(s for s, d, a in edges)
    inc = Counter(d for s, d, a in edges)
    ids = set(pub.values())
    orphan = sorted(ids - set(outc) - set(inc), key=int)
    no_in = sorted(ids - set(inc), key=int)
    no_out = sorted(ids - set(outc), key=int)

    # トップと一覧から各記事への到達段数
    graph = defaultdict(set)
    for src, lst in out_links.items():
        for dst, _ in lst:
            graph[src].add(dst)
    def depth_from(start):
        d = {norm(start): 0}
        q = deque([norm(start)])
        while q:
            u = q.popleft()
            for v in graph.get(u, ()):
                if v not in d:
                    d[v] = d[u] + 1
                    q.append(v)
        return d
    d_top = depth_from(f"{SITE}/")
    d_list = depth_from(f"{SITE}/articles/")

    HUBS = ["19", "546", "42", "304", "278", "23", "289", "315"]
    url_of = {v: k for k, v in pub.items()}

    # カニバリ候補：タイトルの語が重なる組
    def keyset(t):
        return set(re.findall(r"[ぁ-んァ-ヶ一-龥A-Za-z]{2,}", t))
    canni = []
    idl = sorted(ids, key=int)
    for i, a in enumerate(idl):
        for b in idl[i + 1:]:
            ka, kb = keyset(title[a]), keyset(title[b])
            if not ka or not kb:
                continue
            j = len(ka & kb) / len(ka | kb)
            if j >= 0.34:
                canni.append((a, b, round(j, 2), sorted(ka & kb)[:6]))

    L = [f"# 内部リンクのクロール検証 {stamp}\n\n",
         "## まとめ\n\n| 項目 | 値 |\n|---|---|\n",
         f"| 公開記事 | {len(ids)}本 |\n",
         f"| **本文の内部リンク（記事間）** | **{len(edges)}本** |\n",
         "| （参考）テーマが自動で出す関連記事カード | 本文のリンクとは別に集計から除外 |\n",
         f"| 孤立記事（発も被も0） | {len(orphan)}本 {' '.join(orphan) or ''} |\n",
         f"| 被リンク0 | {len(no_in)}本 {' '.join(no_in) or ''} |\n",
         f"| 発リンク0 | {len(no_out)}本 {' '.join(no_out) or ''} |\n",
         f"| リンク切れ | {len(broken)}件 |\n",
         f"| リダイレクト経由 | {len(redirected)}件 |\n",
         f"| 非公開へのリンク | {len(to_unpub)}件 |\n",
         f"| 「こちら」等のアンカー | {len(bad_anchor)}件 |\n",
         f"| 1記事あたり発リンク | 平均 {sum(outc.values())/max(len(outc),1):.1f} "
         f"（最小{min(outc.values()) if outc else 0}・最大{max(outc.values()) if outc else 0}） |\n",
         f"| 1記事あたり被リンク | 平均 {sum(inc.values())/max(len(inc),1):.1f} "
         f"（最小{min(inc.values()) if inc else 0}・最大{max(inc.values()) if inc else 0}） |\n"]

    L.append("\n## ハブ記事への到達段数\n\n"
             "| ハブ | タイトル | 被リンク | トップから | /articles/ から |\n"
             "|---|---|---|---|---|\n")
    for h in HUBS:
        u = url_of.get(h, "")
        L.append(f"| {h} | {title.get(h,'')[:34]} | {inc.get(h,0)} | "
                 f"{d_top.get(u,'到達せず')} | {d_list.get(u,'到達せず')} |\n")

    L.append("\n## 被リンクが多い記事\n\n| 記事 | 被 | 発 | タイトル |\n|---|---|---|---|\n")
    for pid, n in inc.most_common(12):
        L.append(f"| {pid} | {n} | {outc.get(pid,0)} | {title.get(pid,'')[:40]} |\n")

    if broken:
        L.append("\n## リンク切れ\n\n| 元 | 先 | アンカー |\n|---|---|---|\n")
        for s, d, a in broken[:30]:
            L.append(f"| {s} | {d} | {a[:40]} |\n")
    if redirected:
        L.append("\n## リダイレクト経由\n\n| 元 | 書いてあるURL | 実際の着地 |\n|---|---|---|\n")
        for s, d, f in redirected[:30]:
            L.append(f"| {s} | {d[:56]} | {f[:56]} |\n")
    if bad_anchor:
        L.append("\n## アンカーが内容を表していない\n\n| 元 | 先 | アンカー |\n|---|---|---|\n")
        for s, d, a in bad_anchor:
            L.append(f"| {s} | {d} | {a} |\n")

    L.append(f"\n## カニバリ候補（タイトルの語の重なり34%以上）\n\n"
             f"**{len(canni)}組**\n\n| A | B | 重なり | 共通語 |\n|---|---|---|---|\n")
    for a, b, j, ks in sorted(canni, key=lambda x: -x[2])[:20]:
        L.append(f"| {a} {title[a][:24]} | {b} {title[b][:24]} | {j} | "
                 f"{'・'.join(ks)} |\n")
    if not canni:
        L.append("| — | — | — | 該当なし |\n")

    L.append("\n## 記事ごとの発・被\n\n| 記事 | 発 | 被 | タイトル |\n|---|---|---|---|\n")
    for pid in sorted(ids, key=int):
        L.append(f"| {pid} | {outc.get(pid,0)} | {inc.get(pid,0)} | "
                 f"{title.get(pid,'')[:40]} |\n")

    with open(OUT / "LINK_CRAWL.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["from", "to", "anchor"])
        w.writerows(edges)
    (OUT / "LINK_CRAWL.md").write_text("".join(L), encoding="utf-8")
    print(f"\n内部リンク {len(edges)}本 / 孤立 {len(orphan)} / "
          f"切れ {len(broken)} / リダイレクト {len(redirected)}")
    print("→ workspace/seo/LINK_CRAWL.md")


if __name__ == "__main__":
    main()
