#!/usr/bin/env python3
"""
number_audit.py
記事に出てくる数値を全部拾って、**誰の数字なのか**で仕分ける。

命題抽出（claim_extractor）は、動詞に付いた数値しか拾わない。
「貯金は現時点で50万円」「515点で止まった1年3か月」のように
動詞から離れた数値は落ちる（2026-08-08に判明）。
確認の対象にするには、こちらで別に走査する必要がある。

仕分けは2つに大きく分ける。**確認のしかたが違うため。**

  個人の数字 … 支出・貯金・スコア・期間・回数
                → 本人の記録（明細・マイページ）でしか確かめられない
  公式・一般 … サービスの料金・仕様・一般的な統計
                → 公式サイトと出典で確かめる。基準日が要る

**記事は一切修正しない。**

出力: workspace/claims/NUMBERS.md / NUMBERS.csv
"""
import csv
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import claim_extractor as _ce
import quality_rules as _q
import wp_audit as _wa

OUT = Path("affiliate-research-engine/playbook/workspace/claims")

# 単位。claim_extractor の NUM_RE より広い。
# 「70万」「50万」のように円が付かない言い方も拾う
NUM_RE = re.compile(
    r"([0-9][0-9,\.]*(?:万[0-9,]*)?(?:千[0-9,]*)?)\s*"
    r"(万円|円|万|点|時間|年間|年|ヶ月|か月|カ月|週間|日間|日|分|"
    r"回|コマ|本|冊|ページ|社|校|件|人|歳|%|％)")

SELF = r"私|自分|僕"
SPEND = r"払|支払|溶か|課金|買っ|投じ|使っ|かかっ|出費|授業料|月謝|受講料"
SAVE = r"貯金|貯め|預金|手元に"
SCORE = r"TOEIC|スコア|点数|成績"
OFFICIAL = r"月額|プラン|料金|価格|税込|税抜|無料トライアル|無料体験|公式"
GENERAL = r"一般的に|平均|とされ|言われ|研究|統計|データでは|目安|CEFR|とされる"
HYPO = r"としたら|とすると|だとすれば|仮に|たとえば|例えば|計算になる|とする。"

SERVICES = tuple(_q.SERVICE_NAMES)

# 基準日。金額に付いていないと、改定後は訂正ではなく虚偽になる
BASEDATE = r"20[0-9]{2}年[0-9]{1,2}月[0-9]{1,2}日時点|20[0-9]{2}年[0-9]{1,2}月時点"


MONEY = ("万円", "円", "万")


def classify(sent, unit, is_claim):
    """1つの数値が誰の数字かを決める。

    **単位で門を作る。** 文にTOEICが出てくるからといって、
    その文の「2冊」をスコアにしない（2026-08-08に3312件まで膨らんだ原因）。
    金額の話は金額の単位でだけ、スコアの話は点でだけ判定する。

    期間・回数は数が多すぎるので、**体験主張として抽出済みのものだけ**出す。
    「3ヶ月」「1回」を全部並べても確認できない。
    """
    money = unit in MONEY
    svc = [s for s in SERVICES if s in sent]

    if money:
        if re.search(HYPO, sent):
            return "仮定・試算", svc
        if re.search(SAVE, sent):
            return "個人_貯金", svc
        if re.search(SELF, sent) and re.search(SPEND, sent):
            return "個人_支出", svc
        if svc and re.search(OFFICIAL, sent):
            return "公式_料金", svc
        if re.search(SPEND, sent):
            return "個人_支出の可能性", svc
        if svc:
            return "公式_料金", svc
        return "金額_判別不能", svc

    if unit == "点":
        if re.search(HYPO, sent):
            return "仮定・試算", svc
        if re.search(SELF, sent):
            return "個人_スコア", svc
        return "スコア_主語不明", svc

    if re.search(GENERAL, sent):
        return "一般_データ", svc

    # 期間・回数・時間は、体験主張として抽出できているものだけ
    if is_claim and re.search(SELF, sent):
        return "個人_期間回数", svc
    return None, svc


ORDER = ["個人_支出", "個人_貯金", "個人_スコア", "個人_支出の可能性",
         "スコア_主語不明", "個人_期間回数",
         "公式_料金", "一般_データ", "仮定・試算", "金額_判別不能"]

NEEDS = {
    "個人_支出": "クレジットカード・銀行の明細",
    "個人_貯金": "本人の記録（記事に書く必要があるかも要検討）",
    "個人_スコア": "TOEIC公式マイページのスコアと受験日",
    "個人_支出の可能性": "主語を確かめたうえで明細",
    "スコア_主語不明": "誰のスコアかを確かめる",
    "個人_期間回数": "本人の記憶・記録",
    "公式_料金": "公式サイト＋基準日",
    "一般_データ": "出典（研究・統計の一次情報）",
    "仮定・試算": "確認不要（事実主張ではない）。ただし前提の数字は要確認",
    "金額_判別不能": "原文を読んで、誰の金額かを決める",
}


def claim_sentences():
    """CLAIMS.csv で体験主張と判定された文。期間・回数の絞り込みに使う。"""
    f = OUT / "CLAIMS.csv"
    if not f.exists():
        return set()
    return {r["sentence"][:50] for r in csv.DictReader(f.open(encoding="utf-8"))
            if r["experience"] in ("yes", "possible")}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    posts = _wa.published()
    print(f"公開中 {len(posts)}本から数値を拾う\n")

    claims = claim_sentences()
    print(f"体験主張の文 {len(claims)}件を、期間・回数の絞り込みに使う")
    rows, seen = [], set()
    for p in posts:
        pid, link = p["id"], p.get("link", "")
        title = re.sub(r"<[^>]+>", "", p["title"]["rendered"])
        html = p.get("content", {}).get("rendered", "")
        for tag, reason, ss, _rest, _aff in _ce.blocks(html):
            if reason:
                continue
            for sent in ss:
                is_claim = sent[:50] in claims
                for m in NUM_RE.finditer(sent):
                    val, unit = m.group(1), m.group(2)
                    kind, svc = classify(sent, unit, is_claim)
                    if kind is None:
                        continue
                    key = (kind, f"{val}{unit}", sent[:60])
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append({
                        "kind": kind, "value": f"{val}{unit}", "unit": unit,
                        "services": "・".join(svc),
                        "has_basedate": "yes" if re.search(BASEDATE, sent) else "",
                        "post_id": pid, "title": title[:40], "url": link,
                        "sentence": sent[:220],
                        "needs": NEEDS.get(kind, ""),
                        "confirmation": "",
                    })

    rows.sort(key=lambda r: (ORDER.index(r["kind"]) if r["kind"] in ORDER else 99,
                             r["unit"], r["value"]))
    with open(OUT / "NUMBERS.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    cnt = Counter(r["kind"] for r in rows)
    L = [f"# 数値を伴う主張の一覧 {date.today().isoformat()}\n\n",
         f"公開中 {len(posts)}本 / 数値 **{len(rows)}件**\n\n",
         "**確認のしかたが違うので、個人の数字と公式・一般の数字を分けている。**\n\n",
         "| 種類 | 件数 | 何で確かめるか |\n|---|---|---|\n"]
    for k in ORDER:
        if cnt.get(k):
            L.append(f"| {k} | {cnt[k]} | {NEEDS[k]} |\n")

    L.append("\n---\n\n# 個人の数字（本人の記録でしか確かめられない）\n\n")
    personal = ["個人_支出", "個人_貯金", "個人_スコア",
                "個人_支出の可能性", "スコア_主語不明", "個人_期間回数"]
    for k in personal:
        sel = [r for r in rows if r["kind"] == k]
        if not sel:
            continue
        L.append(f"\n## {k}（{len(sel)}件）\n\n")
        L.append("| 数値 | 記事 | 元文 |\n|---|---|---|\n")
        for r in sel:
            s = r["sentence"].replace("|", "｜")[:120]
            L.append(f"| **{r['value']}** | {r['post_id']} | {s} |\n")

    L.append("\n---\n\n# 公式・一般の数字（一次情報と基準日で確かめる）\n\n")
    for k in ["公式_料金", "一般_データ"]:
        sel = [r for r in rows if r["kind"] == k]
        if not sel:
            continue
        nb = [r for r in sel if not r["has_basedate"]]
        L.append(f"\n## {k}（{len(sel)}件・うち基準日なし **{len(nb)}件**）\n\n")
        L.append("| 数値 | 基準日 | サービス | 記事 | 元文 |\n|---|---|---|---|---|\n")
        for r in sel:
            s = r["sentence"].replace("|", "｜")[:100]
            L.append(f"| **{r['value']}** | {'あり' if r['has_basedate'] else '**なし**'} "
                     f"| {r['services'] or '—'} | {r['post_id']} | {s} |\n")

    L.append("\n---\n\n# 仮定・試算（事実主張ではない）\n\n")
    for r in [x for x in rows if x["kind"] == "仮定・試算"]:
        L.append(f"- **{r['value']}** [{r['post_id']}] {r['sentence'][:110]}\n")

    L.append("\n---\n\n# 金額だが誰の数字か決められない（原文を読んで決める）\n\n")
    for r in [x for x in rows if x["kind"] == "金額_判別不能"]:
        L.append(f"- **{r['value']}** [{r['post_id']}] {r['sentence'][:110]}\n")

    (OUT / "NUMBERS.md").write_text("".join(L), encoding="utf-8")
    print(f"数値 {len(rows)}件")
    for k in ORDER:
        if cnt.get(k):
            print(f"  {cnt[k]:>4}件  {k}")


if __name__ == "__main__":
    main()
