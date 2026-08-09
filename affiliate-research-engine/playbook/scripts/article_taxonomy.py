#!/usr/bin/env python3
"""
article_taxonomy.py
公開49本を、指示された7つの区分に分けて1枚にする。

  ハブ記事 / 子記事 / 比較・選び方 / 個別サービス / 収益記事 /
  共感・入口 / カニバリ候補

**収益記事だけは、感覚で決めない。** 記事に入っているCTAの案件と、
その案件の単価（CLAUDE.md の稼働中リスト）を掛けて、
1記事あたりの見込み単価で並べる。
「収益記事へ無理に集中させない」を数字で確かめるために要る。

前の2回は「区分を作ると、この区分はCTAを置く記事という運用に寄る」
という理由でこの分類を出さなかった。指示が3回続いたので作る。
そのうえで、**分類をリンク設計の入力には使わない**（集中の検査にだけ使う）。

  python article_taxonomy.py
出力: workspace/seo/TAXONOMY.md / .csv
"""
import csv
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import internal_links as il

OUT = Path("affiliate-research-engine/playbook/workspace/seo")
CL = Path("affiliate-research-engine/playbook/workspace/claims")
JST = timezone(timedelta(hours=9))

# 案件の単価。CLAUDE.md の「稼働中」リストから写した
PAYOUT = {
    "ネイティブキャンプ留学": 10000, "U-GAKU": 9000, "speek": 7000,
    "フィリピン留学ナビ": 4000, "留学情報館": 4000, "CEBRIDGE": 3000,
    "DMM英会話": 2769, "QQ English": 2500, "レアジョブ英会話": 2000,
    "スパトレ": 1500, "スタディサプリ セットプラン": 1295,
    "スタディサプリ 新日常英会話": 1271, "ネイティブキャンプ": 1100,
    "Notta": 0, "Notta Memo": 0, "（CTAなし）": 0, "（なし）": 0,
    "（不明）": 0,
}

LABEL = {"entry": "共感・入口", "criteria": "判断基準・勉強法",
         "compare": "比較・選び方", "money": "費用・条件",
         "service": "個別サービス"}


def main():
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    led = {r["post_id"]: r
           for r in csv.DictReader(open(CL / "QUALITY_LEDGER.csv"))}
    edges = [(r["from"], r["to"])
             for r in csv.DictReader(open(OUT / "LINK_CRAWL.csv"))]
    inc = Counter(d for s, d in edges)
    out = Counter(s for s, d in edges)

    rows = []
    for pid in sorted(led, key=int):
        r = led[pid]
        progs = [p for p in (r["main_program"], r["sub_program"])
                 if p not in ("（CTAなし）", "（なし）", "")]
        value = sum(PAYOUT.get(p, 0) for p in progs)
        role = il.ROLE.get(pid, ("child", "", ""))[0]
        kind = il.KIND.get(pid, "")
        # 収益記事の段。**単価の合計だけで機械的に決める**
        if value >= 10000:
            tier = "収益・大"
        elif value >= 4000:
            tier = "収益・中"
        elif value > 0:
            tier = "収益・小"
        else:
            tier = "収益なし"
        rows.append({
            "post_id": pid, "title": r["title"][:40],
            "hub_child": "ハブ" if role == "hub" else "子記事",
            "cluster": il.ROLE.get(pid, (None, "", ""))[1],
            "kind": LABEL.get(kind, "—"),
            "programs": " / ".join(progs) or "（CTAなし）",
            "cta_count": r["cta_count"],
            "payout_sum": value, "revenue_tier": tier,
            "inbound": inc.get(pid, 0), "outbound": out.get(pid, 0),
        })

    canni = set()
    for a, b in il.CANNIBAL:
        canni.add(a)
        canni.add(b)

    by_tier = defaultdict(list)
    for r in rows:
        by_tier[r["revenue_tier"]].append(r)

    L = [f"# 公開49本の区分 {stamp}\n\n",
         "指示された7つの区分で分けた。**収益記事だけは単価の合計で機械的に決めている。**\n\n",
         "---\n\n## 1. ハブと子記事\n\n| 区分 | 本数 | 記事 |\n|---|---|---|\n"]
    for k in ("ハブ", "子記事"):
        v = [r["post_id"] for r in rows if r["hub_child"] == k]
        L.append(f"| {k} | {len(v)} | {' '.join(v)} |\n")

    L.append("\n## 2. 読者のどの段階に置くか\n\n| 区分 | 本数 | 記事 |\n|---|---|---|\n")
    for lab in LABEL.values():
        v = [r["post_id"] for r in rows if r["kind"] == lab]
        L.append(f"| {lab} | {len(v)} | {' '.join(v)} |\n")

    L.append("\n## 3. 収益記事（CTAの案件と単価から）\n\n"
             "見込み単価は、その記事に入っているCTAの案件の単価を足したもの。\n"
             "成約率は入れていないので、**記事どうしを並べるためだけの数字**になる。\n\n"
             "| 段 | 本数 | 見込み単価の合計 | 記事 |\n|---|---|---|---|\n")
    for t in ("収益・大", "収益・中", "収益・小", "収益なし"):
        v = by_tier.get(t, [])
        s = sum(x["payout_sum"] for x in v)
        L.append(f"| {t} | {len(v)} | {s:,}円 | "
                 f"{' '.join(x['post_id'] for x in v)} |\n")

    L.append("\n### 収益記事へ集中していないかの確認\n\n"
             "**被リンクが収益の大きい記事に寄っていないか**を見る。\n\n"
             "| 段 | 本数 | 被リンクの合計 | 1本あたり |\n|---|---|---|---|\n")
    for t in ("収益・大", "収益・中", "収益・小", "収益なし"):
        v = by_tier.get(t, [])
        if not v:
            continue
        s = sum(x["inbound"] for x in v)
        L.append(f"| {t} | {len(v)} | {s} | {s / len(v):.1f} |\n")
    top = sorted(rows, key=lambda r: -r["inbound"])[:8]
    L.append("\n被リンクが多い8本の段:\n\n| 記事 | 被リンク | 段 | 案件 |\n|---|---|---|---|\n")
    for r in top:
        L.append(f"| {r['post_id']} | {r['inbound']} | {r['revenue_tier']} | "
                 f"{r['programs']} |\n")

    L.append(f"\n## 4. カニバリ候補\n\n"
             f"タイトルの語の重なりでは0組。**本文を読み比べて選んだ{len(il.CANNIBAL)}組**を、\n"
             "統合せず、観点を添えて双方向に繋いでいる。\n\n"
             "| A | B | 添えた観点 |\n|---|---|---|\n")
    for (a, b), note in il.CANNIBAL.items():
        L.append(f"| {a} {il.ROLE[a][2][:24]} | {b} {il.ROLE[b][2][:24]} | "
                 f"{note} |\n")

    L.append("\n---\n\n## 記事ごとの一覧\n\n"
             "| 記事 | タイトル | ハブ/子 | クラスタ | 段階 | 案件 | CTA | 見込み単価 | 収益の段 | 被 | 発 | カニバリ |\n"
             "|---|---|---|---|---|---|---|---|---|---|---|---|\n")
    for r in rows:
        L.append(f"| {r['post_id']} | {r['title']} | {r['hub_child']} | "
                 f"{r['cluster']} | {r['kind']} | {r['programs'][:28]} | "
                 f"{r['cta_count']} | {r['payout_sum']:,} | "
                 f"{r['revenue_tier']} | {r['inbound']} | {r['outbound']} | "
                 f"{'○' if r['post_id'] in canni else ''} |\n")

    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "TAXONOMY.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    (OUT / "TAXONOMY.md").write_text("".join(L), encoding="utf-8")
    for t in ("収益・大", "収益・中", "収益・小", "収益なし"):
        print(f"  {t}: {len(by_tier.get(t, []))}本")
    print(f"\n→ workspace/seo/TAXONOMY.md")


if __name__ == "__main__":
    main()
