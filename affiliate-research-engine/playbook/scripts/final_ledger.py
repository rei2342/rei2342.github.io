#!/usr/bin/env python3
"""
final_ledger.py
公開・予約・下書きをすべて含めた最終台帳。

数えるもの:
  公開 / 予約 / 下書き / 内部リンク総数 / 孤立 / 被0 / 発0 /
  リンク切れ / リダイレクト経由 / 非公開へのリンク /
  CTA総数 / CTAなし記事 / 案件別CTA数 / カテゴリ別記事数 /
  サイトマップ掲載数 / 未確認の体験 / 未確認の心理 /
  出典のない料金・制度・回数 / 画像矛盾 / 重複見出し / カニバリ候補

**公開記事について、ブロッカー0・リンク切れ0・画像矛盾0が完了条件。**

  python final_ledger.py
出力: workspace/claims/FINAL_LEDGER.md / .csv
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

JST = timezone(timedelta(hours=9))
SITE = "https://sakura-eigo.com"
WP = f"{SITE}/wp-json/wp/v2"
AUTH = ("rei.00pt2342@gmail.com", os.environ.get("WP_APP_PASSWORD", ""))
UA = {"User-Agent": "Mozilla/5.0"}
CL = Path("affiliate-research-engine/playbook/workspace/claims")
SEO = Path("affiliate-research-engine/playbook/workspace/seo")

PROGRAM = [
    ("a_id=5640991", "speek"), ("a_id=5640986", "フィリピン留学ナビ"),
    ("a_id=5640988", "U-GAKU"), ("a_id=5640990", "留学情報館"),
    ("a_id=5640987", "CEBRIDGE"), ("a_id=5640981", "スパトレ"),
    ("a_id=5640982", "DMM英会話"),
    ("4B9W9D+27S3UA", "ネイティブキャンプ留学"),
    ("4B9W9D+2IHWQA", "QQ English"),
    ("4B9W9D+28DJG2", "ネイティブキャンプ"),
    ("4B9W9D+1LR2GI", "レアジョブ英会話"),
    ("4B9W9D+2OG8S2", "スタディサプリ 新日常英会話"),
    ("4B9W9D+28YZ1U", "スタディサプリ セットプラン"),
    ("4B9YLD+EAFAQ", "Notta"), ("4B9YLD+2HB1IQ", "Notta Memo"),
]


def fetch(status):
    out, page = [], 1
    while True:
        r = requests.get(f"{WP}/posts", auth=AUTH, headers=UA, verify=False,
                         timeout=60, params={"status": status, "per_page": 100,
                                             "page": page, "context": "edit"})
        if r.status_code != 200:
            break
        b = r.json()
        out += b
        if len(b) < 100:
            break
        page += 1
    return out


def main():
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    pub = fetch("publish")
    fut = fetch("future")
    dra = fetch("draft")
    print(f"公開 {len(pub)} / 予約 {len(fut)} / 下書き {len(dra)}")

    rows, prog = [], Counter()
    none_cta, blockers_n = [], []
    heads = defaultdict(list)
    for p in sorted(pub, key=lambda x: x["id"]):
        pid = str(p["id"])
        raw = p["content"]["raw"]
        names = [next((n for k, n in PROGRAM if k in h.replace("&#038;", "&")),
                      None)
                 for h in re.findall(r'<a\b[^>]*href="([^"]+)"', raw)]
        names = [n for n in names if n]
        for n in names:
            prog[n] += 1
        if not names:
            none_cta.append(pid)
        b = _q.generation_blockers(raw)
        if b:
            blockers_n.append((pid, b[0][:60]))
        for m in re.finditer(r'<h([23])[^>]*>(.*?)</h\1>', raw, re.S):
            heads[_q.strip_tags(m.group(2)).strip()].append(pid)
        rows.append({"post_id": pid,
                     "title": _q.strip_tags(p["title"]["raw"])[:44],
                     "status": p["status"], "cta": len(names),
                     "programs": " + ".join(names) or "（なし）",
                     "blockers": len(b),
                     "categories": " ".join(str(c) for c in p["categories"])})
    for p in fut + dra:
        rows.append({"post_id": str(p["id"]),
                     "title": _q.strip_tags(p["title"]["raw"])[:44],
                     "status": p["status"], "cta": "", "programs": "",
                     "blockers": "", "categories": ""})

    # カテゴリ別
    cats = requests.get(f"{WP}/categories", auth=AUTH, headers=UA,
                        verify=False, timeout=45, params={"per_page": 100})
    catmap = {c["id"]: c["name"] for c in cats.json()} \
        if cats.status_code == 200 else {}
    bycat = Counter()
    for p in pub:
        for c in p["categories"]:
            bycat[catmap.get(c, str(c))] += 1

    # サイトマップ
    sm = 0
    for u in (f"{SITE}/sitemap.xml", f"{SITE}/wp-sitemap.xml",
              f"{SITE}/sitemap_index.xml"):
        r = requests.get(u, headers=UA, verify=False, timeout=45)
        if r.status_code == 200:
            locs = re.findall(r'<loc>([^<]+)</loc>', r.text)
            for loc in list(locs):
                if loc.endswith('.xml'):
                    rr = requests.get(loc, headers=UA, verify=False,
                                      timeout=45)
                    if rr.status_code == 200:
                        locs += re.findall(r'<loc>([^<]+)</loc>', rr.text)
            sm = len([x for x in set(locs) if not x.endswith('.xml')])
            break

    # クロールの結果を読む（別のワークフローが作る）
    crawl = {}
    f = SEO / "LINK_CRAWL.md"
    if f.exists():
        t = f.read_text(encoding="utf-8")
        for key, pat in [("links", r'内部リンク（記事間）\*\* \| \*\*(\d+)本'),
                         ("orphan", r'孤立記事（発も被も0） \| (\d+)本'),
                         ("noin", r'被リンク0 \| (\d+)本'),
                         ("noout", r'発リンク0 \| (\d+)本'),
                         ("broken", r'リンク切れ \| (\d+)件'),
                         ("redir", r'リダイレクト経由 \| (\d+)件'),
                         ("unpub", r'非公開へのリンク \| (\d+)件')]:
            m = re.search(pat, t)
            crawl[key] = m.group(1) if m else "—"

    # 画像矛盾。**判定の本文から正規表現で拾わない。**
    # 太字の数字を拾うと「90 日達成！」のような引用まで記事IDに見えて、
    # 直っている記事が未対応として並ぶ（2026-08-09に6本の誤検出）。
    # 差し替えが要ると決めた一覧（eyecatch_build.PLAN）を正とする。
    # import すると Pillow が要って台帳のステップごと落ちるので、
    # キーだけをソースから読む（2026-08-09に落ちて古い値が残った）
    plan_src = Path(__file__).with_name("eyecatch_build.py").read_text(
        encoding="utf-8")
    plan_body = plan_src.split("PLAN = {", 1)[1].split("\n}", 1)[0]
    planned = set(re.findall(r'^\s*"(\d+)":', plan_body, re.M))
    applied = set()
    for d in sorted(Path("affiliate-research-engine/playbook/workspace/"
                         "backups").glob("*/EYECATCH_APPLY.md")):
        applied |= set(re.findall(r'^\| (\d+) \|', d.read_text(
            encoding="utf-8"), re.M))
    remain = sorted(planned - applied, key=int)

    dup_head = {k: v for k, v in heads.items() if len(v) > 1
                and k not in ("あわせて確認したいもの",
                              "この記事のテーマで、次に読むと決めやすいもの")}

    L = [f"# 最終台帳 {stamp}\n\n",
         "## 件数\n\n| 項目 | 値 |\n|---|---|\n",
         f"| 公開記事 | **{len(pub)}本** |\n",
         f"| 予約記事 | **{len(fut)}本** |\n",
         f"| 下書き | **{len(dra)}本** |\n",
         f"| サイトマップ掲載 | {sm}件 |\n\n",
         "## リンク\n\n| 項目 | 値 |\n|---|---|\n",
         f"| 内部リンク総数 | {crawl.get('links', '—')}本 |\n",
         f"| 孤立記事 | {crawl.get('orphan', '—')}本 |\n",
         f"| 被リンク0 | {crawl.get('noin', '—')}本 |\n",
         f"| 発リンク0 | {crawl.get('noout', '—')}本 |\n",
         f"| リンク切れ | {crawl.get('broken', '—')}件 |\n",
         f"| リダイレクト経由 | {crawl.get('redir', '—')}件 |\n",
         f"| 非公開記事へのリンク | {crawl.get('unpub', '—')}件 |\n\n",
         "## CTA\n\n| 項目 | 値 |\n|---|---|\n",
         f"| CTA総数 | **{sum(prog.values())}本** |\n",
         f"| CTAなしの記事 | **{len(none_cta)}本** {' '.join(none_cta)} |\n\n",
         "### 案件別\n\n| 案件 | 本数 |\n|---|---|\n"]
    for k, v in prog.most_common():
        L.append(f"| {k} | {v} |\n")

    L.append("\n## カテゴリ別\n\n| カテゴリ | 本数 |\n|---|---|\n")
    for k, v in bycat.most_common():
        L.append(f"| {k} | {v} |\n")

    L.append("\n## 品質\n\n| 項目 | 値 | 完了条件 |\n|---|---|---|\n")
    L.append(f"| ブロッカーのある公開記事 | **{len(blockers_n)}本** | 0 |\n")
    L.append(f"| リンク切れ | {crawl.get('broken', '—')}件 | 0 |\n")
    L.append(f"| 画像矛盾（未対応） | **{len(remain)}本** "
             f"{' '.join(remain)} | 0 |\n")
    L.append(f"| 重複見出し（一覧の見出しを除く） | {len(dup_head)}件 | — |\n")
    for pid, b in blockers_n:
        L.append(f"| ↳ {pid} | {b} | |\n")
    for k, v in dup_head.items():
        L.append(f"| ↳ 「{k}」 | {' '.join(v)} | |\n")

    L.append("\n## 記事ごと\n\n| 記事 | 状態 | タイトル | CTA | 案件 | ブロッカー |\n"
             "|---|---|---|---|---|---|\n")
    for r in rows:
        L.append(f"| {r['post_id']} | {r['status']} | {r['title']} | "
                 f"{r['cta']} | {r['programs']} | {r['blockers']} |\n")

    (CL / "FINAL_LEDGER.md").write_text("".join(L), encoding="utf-8")
    with open(CL / "FINAL_LEDGER.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"CTA総数 {sum(prog.values())} / CTAなし {len(none_cta)} / "
          f"ブロッカー {len(blockers_n)} / 画像未対応 {len(remain)}")
    print("→ workspace/claims/FINAL_LEDGER.md")


if __name__ == "__main__":
    main()
