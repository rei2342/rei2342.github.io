#!/usr/bin/env python3
"""
check_rewrites.py
workspace/rewrites/ の生成物を、反映時とまったく同じ検査にかけて一覧する。

手で項目を並べ直すと検査漏れが起きる（「構造」の重複を見落として
合格と報告してしまった）。判定は article_rewriter.audit() だけを使い、
このスクリプトは表示に徹する。

  MIN_CHARS=6000 python .../check_rewrites.py 315,305,272
  引数を省くと rewrites/ にある全ファイルを見る。
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import article_rewriter as _ar
import affiliate_inserter as _ai

SRC = Path("affiliate-research-engine/playbook/workspace/rewrites")


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    ids = [x for x in arg.replace(" ", "").split(",") if x]

    files = []
    for p in sorted(SRC.glob("*.html")):
        pid = p.name.split("_")[0]
        if ids and pid not in ids:
            continue
        files.append((pid, p))

    if not files:
        print("対象なし")
        return

    # 1記事に複数ファイルがあると反映時に取り違えるので、ここでも警告する
    seen = {}
    for pid, p in files:
        seen.setdefault(pid, []).append(p.name)
    for pid, names in seen.items():
        if len(names) > 1:
            print(f"★ [{pid}] 生成物が{len(names)}個: {', '.join(names)}")

    ok = 0
    print(f"\n{'ID':>5}{'字数':>7}{'H2':>4}{'リンク':>7}  判定（audit と同一）")
    print("-" * 60)
    for pid, p in files:
        html = p.read_text(encoding="utf-8")
        head = re.match(r"^<!--(.*?)-->", html, flags=re.DOTALL)
        title = head.group(1).split("|")[1].strip() if head and "|" in head.group(1) else ""
        body = re.sub(r"^<!--.*?-->\s*", "", html, count=1, flags=re.DOTALL)

        # 反映時と同じく、CTAボックスを付け直した状態で検査する
        body = _ai.strip_box(body) + _ai.build_cta(_ai.classify_full(title, body))[0]

        issues = _ar.audit(body)
        text = re.sub(r"<[^>]+>", "", _ai.strip_box(body))
        links = len(re.findall(r"af\.moshimo\.com/af/c/click|px\.a8\.net/svt/ejp", body))
        h2 = len(re.findall(r"<h2", body))
        if not issues:
            ok += 1
        print(f"{pid:>5}{len(text):>7}{h2:>4}{links:>7}  "
              f"{'合格' if not issues else ' / '.join(issues)}")

    print(f"\n合格 {ok}/{len(files)}")


if __name__ == "__main__":
    main()
