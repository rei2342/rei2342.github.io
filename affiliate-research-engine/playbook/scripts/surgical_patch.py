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
# どの記事でも同じ置き換えになるもの。記事ごとのJSONに書かない。
# 生成側は 2026-08-09 に直したが、すでに出ている記事には旧文言が残っている。
# **URLは触らない。アンカーの文言だけ。**
GLOBAL = [
    # フィリピン留学ナビは遷移先URLが特定できず裏取りできていないので中立のまま
    ("→ フィリピン留学ナビの無料相談会に申し込む",
     "→ フィリピン留学ナビ公式サイトで留学プランと相談の申し込み方法を見る"),
    ("→ 国内英語留学U-GAKUで無料オンライン個別相談を予約する",
     "→ 国内英語留学U-GAKUの無料カウンセリングを申し込む"),
    ("→ 留学情報館で無料カウンセリングを申し込む",
     "→ 留学情報館の無料カウンセリングを申し込む"),
    ("→ CEBRIDGEでフィリピン留学の無料カウンセリングを予約する",
     "→ CEBRIDGEでフィリピン留学の無料カウンセリングを申し込む"),
    ("→ DMM英会話のオンライン無料体験レッスンを受けてみる",
     "→ DMM英会話の無料体験レッスンを試す"),
    ("→ レアジョブ英会話（マンツーマン・早朝6時から深夜1時まで）の無料体験レッスンを受ける",
     "→ レアジョブ英会話の7日間無料体験を試す"),
    ("→ スタディサプリENGLISH 新日常英会話コースを無料体験する",
     "→ スタディサプリENGLISH 新日常英会話コースの初回無料体験を試す"),
    ("→ 英語の会議を文字起こしして後から確認する（Notta・無料プランあり）",
     "→ 英語の会議を文字起こしして後から確認する（Notta公式サイト）"),
]

def strip_baked_toc(html):
    """本文に焼き付いた目次プラグインの出力を外す。

    4本（241 281 287 297）は、プラグインが出したHTMLがそのまま
    本文として保存されていた。見出しの文言を変えると目次だけ古くなるし、
    プラグインは描画時に自分で目次を作るので、本文に持つ必要がない。
    """
    i = html.find('<div id="ez-toc-container"')
    if i >= 0:
        depth, j = 0, i
        while j < len(html):
            if html.startswith("<div", j):
                depth += 1
            elif html.startswith("</div>", j):
                depth -= 1
                if depth == 0:
                    j += 6
                    break
            j += 1
        html = (html[:i] + html[j:]).lstrip("\n")
    # 見出しに残るアンカー用の span も外す（描画時に付け直される）
    html = re.sub(r'<span class="ez-toc-section"[^>]*></span>', "", html)
    html = re.sub(r'<span class="ez-toc-section-end"></span>', "", html)
    return html


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
        html = strip_baked_toc(src.read_text(encoding="utf-8"))

        applied, missed = 0, []
        for old, new in GLOBAL:          # 全記事共通の置き換えを先に当てる
            if old in html:
                html = html.replace(old, new)
                applied += 1

        pf = PATCH / f"{pid}.json"
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
