#!/usr/bin/env python3
"""
rewrite_planner.py
確認できなかった体験主張について、**該当箇所の原文をそのまま取り出す**。

修正案は人（と、これを読む生成側）が書く。ここでやるのは、
「どの記事のどの段落に、どの体験表現が入っているか」を、
推測なしで正確に並べることだけ。

CLAIMS.csv と AUDIT_DECISIONS.csv を突き合わせ、
判定が verified 以外のものについて、
  - 該当する段落の全文（前後の段落つき）
  - 段落内でのアフィリンクの有無
  - 見出しの位置（どのH2の下か）
を出す。**記事は一切書き換えない。**

出力: workspace/claims/REWRITE_CONTEXT.md
"""
import csv
import os
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import quality_rules as _q
import wp_audit as _wa

OUT = Path("affiliate-research-engine/playbook/workspace/claims")

# 体験表現の動詞。段落内のどこに手を入れるかを示すため、位置ごと出す
CLAIM_VERBS = r"申し込ん|申し込む|申込|受けた|受けて|受ける|使った|使って|試した|試して|試している|通った|払った|契約した|登録した"

BLOCK_RE = re.compile(r"<(p|li|h2|h3|h4|blockquote|td)\b[^>]*>(.*?)</\1>",
                      re.DOTALL | re.IGNORECASE)


def targets():
    """AUDIT_DECISIONS.csv から、確認できていない主張の対象語を集める。"""
    f = OUT / "AUDIT_DECISIONS.csv"
    if not f.exists():
        print("AUDIT_DECISIONS.csv が無い")
        return []
    rows = list(csv.DictReader(f.open(encoding="utf-8")))
    keep = [r for r in rows
            if r["decision"] not in ("verified", "false_positive",
                                     "out_of_scope_service")]
    out = []
    for r in keep:
        pids = [p for p in (r.get("post_ids") or "").split() if p]
        out.append({"target": r["target"], "action": r["action_normalized"],
                    "post_ids": pids, "decision": r["decision"],
                    "head": r["sentence_head"], "cid": r["claim_id_at_decision"]})
    return out


def paragraphs(html):
    """(見出し, 種別, 内側HTML, プレーン文) の並び。見出しは直近のものを持ち回る。"""
    out, head = [], ""
    for m in BLOCK_RE.finditer(html):
        tag, inner = m.group(1).lower(), m.group(2)
        text = _q.strip_tags(inner)
        if tag in ("h2", "h3", "h4"):
            head = text
            continue
        if text:
            out.append((head, tag, inner, text))
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    tg = targets()
    if not tg:
        return
    want = sorted({p for t in tg for p in t["post_ids"]})
    print(f"確認できていない主張 {len(tg)}件 / 対象記事 {len(want)}本")

    posts = {str(p["id"]): p for p in _wa.published()}
    L = [f"# 修正対象の原文 {date.today().isoformat()}\n\n",
         "確認が取れなかった体験主張について、**該当段落を原文のまま**並べたもの。\n"
         "修正はしていない。どこに手を入れるかを決めるための材料。\n\n"]

    total = 0
    for t in tg:
        L.append(f"\n---\n\n## {t['cid']} {t['target']}を{t['action']}"
                 f"（判定: {t['decision']}）\n\n")
        for pid in t["post_ids"]:
            p = posts.get(pid)
            if not p:
                L.append(f"### 記事 {pid} … 見つからない（非公開になった可能性）\n\n")
                continue
            title = re.sub(r"<[^>]+>", "", p["title"]["rendered"])
            html = p.get("content", {}).get("rendered", "")
            paras = paragraphs(html)
            hits = [i for i, (_h, _tg, _in, tx) in enumerate(paras)
                    if t["target"] in tx and re.search(CLAIM_VERBS, tx)]
            L.append(f"### 記事 {pid}｜{title}\n\n{p.get('link','')}\n\n")
            if not hits:
                # 対象語だけでも出す。動詞が別表現かもしれない
                hits = [i for i, (_h, _tg, _in, tx) in enumerate(paras)
                        if t["target"] in tx]
                L.append(f"※ 体験動詞つきの段落は無い。"
                         f"対象語を含む段落 {len(hits)}件を出す\n\n")
            for i in hits:
                head, tag, inner, text = paras[i]
                aff = "**アフィリンクあり**" if _q.AFFILIATE_LINK_RE.search(inner) else "アフィリンクなし"
                L.append(f"#### 見出し: {head or '（リード）'}｜`<{tag}>`｜{aff}\n\n")
                for j in (i - 1, i, i + 1):
                    if 0 <= j < len(paras):
                        mark = "**→ 該当**" if j == i else "前後"
                        L.append(f"- {mark}: {paras[j][3]}\n")
                # 段落内のどの語が体験表現か
                vs = sorted({m.group(0) for m in re.finditer(CLAIM_VERBS, text)})
                L.append(f"\n  体験表現: {'・'.join(vs) or '（なし）'}\n\n")
                total += 1
            L.append("\n")

    L.append(f"\n---\n\n該当段落 {total}件\n")
    (OUT / "REWRITE_CONTEXT.md").write_text("".join(L), encoding="utf-8")
    print(f"該当段落 {total}件 → REWRITE_CONTEXT.md")


if __name__ == "__main__":
    main()
