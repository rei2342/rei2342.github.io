#!/usr/bin/env python3
"""
draft_gate.py
生成したドラフトを、WordPressへ送る**前**に検査する。

最上位ルール（2026-08-08）:
  **事実台帳で verified になっていない、さくら固有の過去・現在の事実を
    生成しない。**

引っかかったら、一般論へ自動で書き換えず、**該当文を報告して落とす**。
機械が黙って薄めると、何が消えたのか誰も分からなくなる。

使い方:
  python draft_gate.py <ファイル>...
  終了コード 0 … 通過。WordPressへ送ってよい
  終了コード 1 … 不合格。**送らない**

出力: workspace/drafts/GATE.md（落ちた文の一覧）
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import quality_rules as _q

OUT = Path("affiliate-research-engine/playbook/workspace/drafts")


def check(path):
    body = Path(path).read_text(encoding="utf-8")
    return _q.generation_blockers(body)


def main():
    files = [Path(a) for a in sys.argv[1:] if Path(a).exists()]
    if not files:
        print("検査するファイルがない")
        return 0

    L = [f"# 生成ゲートの結果 {date.today().isoformat()}\n\n",
         "**台帳で verified になっていない、さくら固有の事実を止める。**\n"
         "落ちた文は自動で書き換えない。人が台帳に登録するか、文を消すかを決める。\n\n"]
    ng = 0
    for f in files:
        issues = check(f)
        mark = "❌ 不合格" if issues else "✅ 通過"
        print(f"{mark}  {f.name}  ({len(issues)}件)")
        L.append(f"\n## {mark} {f.name}\n\n")
        if not issues:
            L.append("問題なし。WordPressへ送ってよい。\n")
            continue
        ng += 1
        L.append(f"止めた理由 {len(issues)}件。**この記事はWordPressへ送らない。**\n\n")
        for i in issues:
            print(f"    {i[:120]}")
            L.append(f"- {i}\n")
        L.append("\n直し方は2つだけ。\n\n"
                 "1. その事実が本当なら、`workspace/experience_facts.csv` に "
                 "`fact_id` を作って `verified=yes` にし、記事の該当文へ "
                 "`<!--fact:F00X-->` を付ける\n"
                 "2. 本当かどうか分からないなら、**その文を消す**。"
                 "一般論へ薄めて残さない\n")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "GATE.md").write_text("".join(L), encoding="utf-8")
    print(f"\n不合格 {ng}/{len(files)}本")
    if ng:
        print("**WordPressへは送らない。** 詳細は workspace/drafts/GATE.md")
    return 1 if ng else 0


if __name__ == "__main__":
    sys.exit(main())
