#!/usr/bin/env python3
"""
surgical_report.py
未改修の記事について、**ゲートが止める文だけ**を抜き出す。

個人の数字が1〜3件しかない記事に全面改修は要らない。
該当文だけを直すほうが、検索意図も既存の価値も壊さない。

  POSTS=151,150 python surgical_report.py
出力: workspace/claims/SURGICAL.md
"""
import os
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import quality_rules as _q

POSTS_DIR = Path("affiliate-research-engine/playbook/workspace/claims/posts")
OUT = Path("affiliate-research-engine/playbook/workspace/claims")
DONE = {"310", "304", "282", "521", "32", "272", "149", "131", "37", "23",
        "278", "315", "526", "277", "40", "288", "232", "283"}


def main():
    only = [x.strip() for x in os.environ.get("POSTS", "").split(",") if x.strip()]
    files = sorted(POSTS_DIR.glob("*.html"), key=lambda f: f.stem)
    L = [f"# 該当文だけの修正リスト {date.today().isoformat()}\n\n",
         "改修済みを除いた記事について、**ゲートが止める文だけ**を並べたもの。\n"
         "全面改修ではなく、この文だけを直す。\n\n"]
    tot = Counter()
    n_art = 0
    for f in files:
        pid = f.stem
        if pid in DONE or (only and pid not in only):
            continue
        html = f.read_text(encoding="utf-8")
        blockers = _q.generation_blockers(html)
        cta = _q.cta_claim_gate(html)
        if not blockers and not cta:
            continue
        n_art += 1
        L.append(f"\n---\n\n## 記事 {pid}（{len(blockers)}件 + CTA {len(cta)}件）\n\n")
        for b in blockers:
            m = re.match(r"\[([^\]]+)\]", b)
            if m:
                tot[m.group(1)] += 1
            L.append(f"- {b}\n")
        for c in cta:
            tot["CTAの訴求"] += 1
            L.append(f"- [CTA] {c['reason']}: 「{c['anchor'][:50]}」\n")
        print(f"[{pid}] {len(blockers)}件 + CTA {len(cta)}件")

    head = [f"対象 **{n_art}本** / 指摘 **{sum(tot.values())}件**\n\n",
            "| 種類 | 件数 |\n|---|---|\n"]
    for k, v in tot.most_common():
        head.append(f"| {k} | {v} |\n")
    L = L[:2] + head + L[2:]
    (OUT / "SURGICAL.md").write_text("".join(L), encoding="utf-8")
    print(f"\n対象 {n_art}本 / 指摘 {sum(tot.values())}件 → SURGICAL.md")
    for k, v in tot.most_common():
        print(f"  {v:>3}  {k}")


if __name__ == "__main__":
    main()
