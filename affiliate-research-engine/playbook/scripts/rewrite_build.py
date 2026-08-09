#!/usr/bin/env python3
"""
rewrite_build.py
改修本文（<id>.body.html）にCTAを付けて <id>.html を作り、全ゲートを通す。

CTAを手で書くと、案件ごとの訴求が台帳とずれる。
**箱は必ず affiliate_inserter から生成する。**

`<id>.topic` に1行でトピック名を書くと、そのトピックの案件を使う。
無ければタイトルと本文から自動判定する。

  python rewrite_build.py            … 全部
  IDS=292,289 python rewrite_build.py … 指定のみ
出力: workspace/claims/rewrites/<id>.html / BUILD.md
"""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import affiliate_inserter as _ai
import quality_rules as _q

SRC = Path("affiliate-research-engine/playbook/workspace/claims/rewrites")
TITLES = SRC / "TITLES.json"
IDS = [x.strip() for x in os.environ.get("IDS", "").split(",") if x.strip()]


def main():
    titles = json.loads(TITLES.read_text(encoding="utf-8")) if TITLES.exists() else {}
    bodies = sorted(SRC.glob("*.body.html"),
                    key=lambda p: p.name)
    L = ["# 改修本文のビルド\n\n",
         "本文にCTAを付けて、全ゲートを通した結果。\n"
         "**1件でも残っていたらWordPressへは送らない。**\n\n",
         "| 記事 | トピック | 案件 | 字数 | ゲート |\n|---|---|---|---|---|\n"]
    ng = 0
    for b in bodies:
        pid = b.name.split(".")[0]
        if IDS and pid not in IDS:
            continue
        body = b.read_text(encoding="utf-8").strip()
        tf = SRC / f"{pid}.topic"
        topic = (tf.read_text(encoding="utf-8").strip() if tf.exists()
                 else _ai.classify_full(titles.get(pid, ""), body))
        # 記事ごとにCTAを選ぶ。`<id>.cta` に案件キーを改行区切りで書くと、
        # トピックの既定より優先する。**本文で役割を説明した案件だけ置く。**
        cf = SRC / f"{pid}.cta"
        if cf.exists():
            keys = [x.strip() for x in cf.read_text(encoding="utf-8").split()
                    if x.strip()]
            if keys:
                items = "\n".join(f"<p>{_ai.LINKS[k][1]}</p>" for k in keys)
                cta = ("\n<hr>\n<div style=\"background:#f9f9f9;"
                       "border-left:4px solid #27ae60;padding:16px 20px;"
                       "margin:32px 0\">\n"
                       f"<p style=\"margin-top:0;font-weight:bold\">"
                       f"{_ai.CTA_HEADING}</p>\n" + items +
                       "\n<p style=\"margin-bottom:0;font-size:0.8em;"
                       f"color:#999\">{_ai.CTA_NOTE}<br>"
                       "※本記事にはアフィリエイトリンクが含まれます（PR）</p>\n"
                       "</div>")
                progs = keys
            else:
                cta, progs = "", ["（CTAなし）"]
        else:
            cta, progs = _ai.build_cta(topic)
        html = _ai.strip_box(body) + cta

        issues = _q.generation_blockers(html)
        n = len(re.sub(r"<[^>]+>", "", _ai.strip_box(html)))
        mark = "✅ 0件" if not issues else f"❌ {len(issues)}件"
        L.append(f"| {pid} | {topic} | {'・'.join(progs)} | {n} | {mark} |\n")
        print(f"[{pid}] {topic} {progs} {n}字 {mark}")
        if issues:
            ng += 1
            for i in issues:
                L.append(f"| | | | | {i} |\n")
                print(f"    - {i}")
            continue
        (SRC / f"{pid}.html").write_text(html, encoding="utf-8")

    L.append(f"\n**ゲートで止まった記事 {ng}本**\n")
    (SRC / "BUILD.md").write_text("".join(L), encoding="utf-8")
    print(f"\n止まった {ng}本 → rewrites/BUILD.md")
    return 1 if ng else 0


if __name__ == "__main__":
    sys.exit(main())
