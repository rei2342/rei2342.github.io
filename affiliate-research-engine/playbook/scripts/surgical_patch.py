#!/usr/bin/env python3
"""
surgical_patch.py
旧設定の残る箇所だけを差し替える。**記事を書き直さない。**

改修すべき箇所が数個しかない記事まで全文を書き直すと、
検索意図に合っていた部分まで壊れる。文単位で置き換える。

置き換えは `workspace/claims/patches/<id>.json` に書く。

    [
      {"old": "27歳の私が、いつか…", "new": "英語から離れていた期間が長い場合、…"},
      {"old": "…", "new": ""}          ← new が空なら削除
    ]

  IDS=241,150 python surgical_patch.py        … 残っている問題を出すだけ
  APPLY=true IDS=241 python surgical_patch.py … パッチを当てて rewrites/ に書く
出力: workspace/claims/patches/REPORT.md / rewrites/<id>.html
"""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import quality_rules as _q

CL = Path("affiliate-research-engine/playbook/workspace/claims")
POSTS, PATCH, OUT = CL / "posts", CL / "patches", CL / "rewrites"
IDS = [x.strip() for x in os.environ.get("IDS", "").split(",") if x.strip()]
APPLY = os.environ.get("APPLY", "false").lower() == "true"

# 旧ペルソナ設定。ゲートに掛からない疑問文・体言止めも拾う
LEGACY = re.compile(
    r"2[0-9]\s*歳|30歳まで|30歳になる前|あと\s*[0-9]+\s*年|残り\s*[0-9]+\s*年|"
    r"5年後回し|営業事務|さくらの英語挑戦記|さくらが確かめた|すべて無料")


def problems(html):
    """ゲートの指摘と、旧設定の残存を1つにまとめて返す。"""
    out = [("ゲート", b) for b in _q.generation_blockers(html)]
    text = _q.strip_tags(html)
    for s in re.split(r"(?<=[。！？])", text):
        s = s.strip()
        if s and LEGACY.search(s):
            out.append(("旧設定", s[:160]))
    return out


def main():
    PATCH.mkdir(parents=True, exist_ok=True)
    L = ["# 文単位の差し替え\n\n",
         "旧設定の残る箇所だけを置き換える。記事全体は書き直さない。\n\n"]
    ng = 0
    ids = IDS or sorted(p.name.split(".")[0]
                        for p in POSTS.glob("*.raw.html"))
    for pid in ids:
        # **rendered ではなく raw を使う。**
        # rendered には目次プラグインが差し込んだHTMLが混ざるので、
        # それを本文として書き戻すと目次が焼き付く
        src = POSTS / f"{pid}.raw.html"
        if not src.exists():
            print(f"[{pid}] 生の本文が無い（article_dump を先に回す）")
            continue
        html = src.read_text(encoding="utf-8")

        pf = PATCH / f"{pid}.json"
        applied, missed = 0, []
        if pf.exists():
            for r in json.loads(pf.read_text(encoding="utf-8")):
                if r["old"] not in html:
                    missed.append(r["old"][:60])
                    continue
                html = html.replace(r["old"], r["new"])
                applied += 1

        left = problems(html)
        L.append(f"\n## 記事{pid}\n\n"
                 f"- 当てたパッチ: {applied}件"
                 + (f" / **見つからなかった: {len(missed)}件**" if missed else "")
                 + f" / 残る問題: **{len(left)}件**\n\n")
        for m in missed:
            L.append(f"  - ⚠️ 元文が見つからない: `{m}`\n")
        for kind, s in left:
            L.append(f"  - [{kind}] {s}\n")

        print(f"[{pid}] パッチ{applied} 未一致{len(missed)} 残り{len(left)}")
        for kind, s in left:
            print(f"    [{kind}] {s[:120]}")

        if left or missed:
            ng += 1
            continue
        if APPLY:
            OUT.mkdir(parents=True, exist_ok=True)
            (OUT / f"{pid}.html").write_text(html, encoding="utf-8")
            print(f"    → rewrites/{pid}.html")

    L.append(f"\n**問題が残る記事 {ng}本**\n")
    (PATCH / "REPORT.md").write_text("".join(L), encoding="utf-8")
    print(f"\n問題が残る {ng}本 → patches/REPORT.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
