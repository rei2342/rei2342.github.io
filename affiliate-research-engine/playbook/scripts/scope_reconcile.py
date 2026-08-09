#!/usr/bin/env python3
"""
scope_reconcile.py
改修の対象範囲を、記事IDのユニークな集合として確定する。

前回の報告は「公開49本 / クリーン9本 / 語りが残る46本」と食い違っていた。
9 + 46 = 55 で 49 を超える。**測った集合が違うものを並べていた**ため。
  - 「クリーン9本」… ローカルの改修版ファイル（rewrites/）を数えた
  - 「46本」      … 公開中の本文を数えた
改修版がまだ反映されていない記事は、両方に入る。

ここでは**公開中の本文だけ**を1つの基準にして、
記事IDの集合として分類する。合計が公開本数と一致することを確かめる。

  python scope_reconcile.py
出力: workspace/claims/SCOPE.md
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import urllib3

urllib3.disable_warnings()
sys.path.insert(0, str(Path(__file__).parent))
import quality_rules as _q
import wp_audit as _wa

CL = Path("affiliate-research-engine/playbook/workspace/claims")
JST = timezone(timedelta(hours=9))

# 全文を書き直した記事。文単位の差し替えとは別物として数える
FULL_REWRITE = {"292", "289", "42", "546", "238", "294"}


def main():
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    posts = _wa.published()
    all_ids = sorted({str(p["id"]) for p in posts}, key=int)
    print(f"公開記事 {len(posts)}本 / ユニークID {len(all_ids)}件")

    held = sorted({p.name.split(".")[0]
                   for p in (CL / "held").glob("*.html")}, key=int)

    narr, other, clean = [], [], []
    detail = {}
    for p in posts:
        pid = str(p["id"])
        html = p.get("content", {}).get("rendered", "")
        blockers = _q.generation_blockers(html)
        n_narr = len([b for b in blockers if "一人称の語り" in b])
        n_other = len(blockers) - n_narr
        detail[pid] = (n_narr, n_other)
        if n_narr:
            narr.append(pid)
        elif n_other:
            other.append(pid)
        else:
            clean.append(pid)

    narr, other, clean = (sorted(x, key=int) for x in (narr, other, clean))
    dup_held = sorted(set(held) & set(clean), key=int)
    held_not_pub = sorted(set(held) - set(all_ids), key=int)

    total = len(narr) + len(other) + len(clean)
    L = [f"# 改修の対象範囲 {stamp}\n\n",
         "**公開中の本文だけを基準にする。** ローカルの改修版ファイルは数えない。\n"
         "前回は測った集合が違うものを並べていて、合計が公開本数を超えていた。\n\n",
         "| 分類 | 件数 | 記事ID |\n|---|---|---|\n",
         f"| 公開記事（全体） | **{len(all_ids)}** | {' '.join(all_ids)} |\n",
         f"| ① 一人称の語りが残る | **{len(narr)}** | {' '.join(narr)} |\n",
         f"| ② 語りは無いが他のブロッカーあり | **{len(other)}** | "
         f"{' '.join(other) or '—'} |\n",
         f"| ③ クリーン（ブロッカー0件） | **{len(clean)}** | {' '.join(clean)} |\n",
         f"\n**①＋②＋③ = {total}**"
         + ("（公開本数と一致）\n\n" if total == len(all_ids)
            else f"（⚠️ 公開本数 {len(all_ids)} と一致しない）\n\n"),
         "---\n\n## 内訳\n\n",
         f"- **全文再構成が済んでいる記事**: {len(FULL_REWRITE & set(clean))}本 "
         f"（{' '.join(sorted(FULL_REWRITE & set(clean), key=int))}）\n",
         f"- **文単位の差し替えだけの記事（held に改修版がある）**: {len(held)}本 "
         f"（{' '.join(held)}）\n",
         f"- **held にあるが公開されていない**: {len(held_not_pub)}本 "
         f"（{' '.join(held_not_pub) or 'なし'}）\n",
         f"- **held にあって既にクリーン**: {len(dup_held)}本 "
         f"（{' '.join(dup_held) or 'なし'}）\n\n"]

    # held に入っていないのに語りが残る記事＝まだ手を付けていない記事
    untouched = sorted(set(narr) - set(held), key=int)
    L.append(f"- **まだ手を付けていない（held にも無く、語りが残る）**: "
             f"**{len(untouched)}本** （{' '.join(untouched)}）\n\n")

    L.append("## 重複の確認\n\n"
             "| 組み合わせ | 件数 |\n|---|---|\n"
             f"| ① と ③ の重複 | {len(set(narr) & set(clean))} |\n"
             f"| ② と ③ の重複 | {len(set(other) & set(clean))} |\n"
             f"| ① と ② の重複 | {len(set(narr) & set(other))} |\n\n"
             "3つは排他なので、すべて0になる。\n\n")

    L.append("---\n\n## 記事ごとの件数\n\n"
             "| 記事 | 一人称の語り | その他 | 状態 |\n|---|---|---|---|\n")
    for pid in all_ids:
        n1, n2 = detail[pid]
        st = ("✅ クリーン" if not n1 and not n2
              else ("🔴 語りが残る" if n1 else "⚠️ その他"))
        mark = " / held" if pid in held else ""
        mark += " / 全文再構成" if pid in FULL_REWRITE else ""
        L.append(f"| {pid} | {n1} | {n2} | {st}{mark} |\n")

    (CL / "SCOPE.md").write_text("".join(L), encoding="utf-8")
    print(f"\n① 語りが残る {len(narr)} / ② その他 {len(other)} / "
          f"③ クリーン {len(clean)} = {total}")
    print(f"まだ手を付けていない: {len(untouched)}本")
    print("→ workspace/claims/SCOPE.md")


if __name__ == "__main__":
    main()
