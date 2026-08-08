#!/usr/bin/env python3
"""
number_plan.py
数値を含む記事について、**記事単位の改修計画の骨組み**を作る。

方針（2026-08-08に確定）:
  **確認済み台帳にない一人称の数字は、原則として公開記事から外す。**

681件を1件ずつ事実確認しない。種類ごとに変換ルールを決めて、
記事ごとに「何を消して何を残すか」を並べる。
記事間で矛盾する「さくらの履歴」を止めるのが目的なので、
**正しいスコアを新しく決めることはしない。**
確認済みの実データが登録されるまで、さくら固有のスコア履歴を持たせない。

**記事は一切修正しない。** 計画を出すだけ。

出力: workspace/claims/NUMBER_PLAN.md
"""
import csv
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import quality_rules as _q
import wp_audit as _wa

OUT = Path("affiliate-research-engine/playbook/workspace/claims")

# 台帳が unknown のときの、種類ごとの処理
RULE = {
    "個人_スコア":       ("削除", "一人称の点数・推移を消す。読者視点の問いに置き換える"),
    "スコアの増減":       ("削除", "「45点動いた」のような伸びの記述を消す"),
    "個人_支出":         ("削除→公式料金か試算", "「払った」を消す。金額を残すなら公式料金か明示した試算にする"),
    "個人_支出の可能性":   ("要判断", "主語を確かめる。さくらの支出なら削除"),
    "個人_貯金":         ("削除", "一人称の残高を消す。必要額の話は相場として書く"),
    "個人_期間回数":      ("削除", "未確認の体験としての数字を消す"),
    "公式_料金":         ("残す", "公式出典と確認日を付ける"),
    "費用の相場":        ("残す", "根拠・対象範囲・基準日を確認して付ける"),
    "費用の見積もり_一人称": ("書き換え", "一人称の試算なら「例」「試算」と明記する"),
    "一般_データ":        ("残す", "一次情報または信頼できる出典を付ける"),
    "仮定・試算":         ("残す", "「例」「試算」と明記する"),
}

# 優先順位。相互に矛盾するTOEICスコアが最優先
PRI = {"個人_スコア": 1, "スコアの増減": 1,
       "個人_貯金": 2, "個人_支出": 2, "個人_支出の可能性": 2,
       "個人_期間回数": 3, "公式_料金": 4,
       "費用の相場": 5, "費用の見積もり_一人称": 5, "一般_データ": 5, "仮定・試算": 5}
PRI_NAME = {1: "① 相互に矛盾するTOEICスコア", 2: "② 貯金・支出など個人のお金",
            3: "③ 利用期間・回数", 4: "④ 公式料金", 5: "⑤ 費用相場・一般データ"}


def intent(title):
    """検索意図。タイトルのかぎ括弧に入っている検索語をそのまま使う。"""
    m = re.search(r"[「『]([^」』]{4,40})[」』]", title)
    return m.group(1) if m else ""


def ctas():
    """記事ID → その記事にあるアフィリンクの文言。LINK_AUDIT.csv から。"""
    f = OUT / "LINK_AUDIT.csv"
    out = defaultdict(list)
    if not f.exists():
        return out
    for r in csv.DictReader(f.open(encoding="utf-8")):
        for pid in r["posts"].split():
            out[pid].append(r["anchor"].replace("→ ", "").strip())
    return out


def actions():
    """CTA_ACTIONS.csv で決めた対応。記事IDごとに引けるようにする。"""
    f = OUT / "CTA_ACTIONS.csv"
    out = defaultdict(list)
    if not f.exists():
        return out
    for r in csv.DictReader(f.open(encoding="utf-8")):
        for pid in r["post_ids"].split():
            out[pid].append((r["service"], r["action"], r["status"]))
    return out


def main():
    nf = OUT / "NUMBERS.csv"
    if not nf.exists():
        print("NUMBERS.csv が無い。先に number_audit.py を回す")
        return
    rows = list(csv.DictReader(nf.open(encoding="utf-8")))
    cta, act = ctas(), actions()

    byp = defaultdict(lambda: defaultdict(list))
    meta = {}
    for r in rows:
        byp[r["post_id"]][r["kind"]].append(r)
        meta[r["post_id"]] = (r["title"], r["url"])

    def pri(p):
        return min([PRI.get(k, 9) for k in byp[p]] or [9])

    order = sorted(byp, key=lambda p: (pri(p),
                                       -sum(len(v) for v in byp[p].values())))

    L = [f"# 数値を含む記事の改修計画 {date.today().isoformat()}\n\n",
         "**方針: 確認済み台帳にない一人称の数字は、原則として公開記事から外す。**\n\n",
         "681件を1件ずつ事実確認しない。種類ごとに変換ルールを決めて適用する。\n"
         "記事は削除しない。検索意図を保ったまま、"
         "**さくら固有の履歴だけ**を外す。\n\n",
         "⚠️ **「さくらの正しいTOEICスコア」を新しく決めない。**\n"
         "確認済みの実データが登録されるまで、さくら固有のスコア履歴を持たせない。\n"
         "これで今後の記事間の矛盾も止まる。\n\n",
         "**本文の自動修正はまだ実行していない。**\n\n",
         "## 種類ごとの処理\n\n| 種類 | 台帳がunknownのとき | 中身 |\n|---|---|---|\n"]
    for k, (how, why) in RULE.items():
        L.append(f"| {k} | **{how}** | {why} |\n")

    L.append(f"\n## 対象記事 {len(order)}本\n\n")
    L.append("| 優先 | 記事 | 数値 | タイトル |\n|---|---|---|---|\n")
    for p in order:
        n = sum(len(v) for v in byp[p].values())
        L.append(f"| {pri(p)} | {p} | {n} | {meta[p][0]} |\n")

    cur = None
    for p in order:
        if pri(p) != cur:
            cur = pri(p)
            L.append(f"\n---\n\n# {PRI_NAME.get(cur, '')}\n")
        title, url = meta[p]
        d = byp[p]
        L.append(f"\n---\n\n## 記事 {p}｜{title}\n\n")
        L.append(f"- **URL**: {url}\n")
        it = intent(title)
        L.append(f"- **検索意図**: {it or '（タイトルに検索語なし。本文から判断が要る）'}\n")

        # 削除する個人体験
        rm = []
        for k in ("個人_スコア", "スコアの増減", "個人_貯金", "個人_支出",
                  "個人_期間回数"):
            for r in d.get(k, []):
                rm.append((k, r["value"], r["sentence"]))
        L.append(f"- **削除する個人の数字**: {len(rm)}件\n")

        keep = sum(len(d.get(k, [])) for k in
                   ("公式_料金", "費用の相場", "一般_データ", "仮定・試算"))
        L.append(f"- **出典を付けて残す数字**: {keep}件\n")

        judge = d.get("個人_支出の可能性", []) + d.get("費用の見積もり_一人称", [])
        L.append(f"- **主語を確かめる数字**: {len(judge)}件\n")

        # 収益導線
        cs = cta.get(p, [])
        acts = act.get(p, [])
        if cs:
            L.append(f"- **収益導線**: {' / '.join(sorted(set(cs)))}\n")
        else:
            L.append("- **収益導線**: アフィリンクなし\n")
        for svc, a, st in acts:
            L.append(f"  - ⚠️ **{svc} は「{a}」で決定済み**（{st}）\n")

        if rm:
            L.append("\n### 削除する個人の数字\n\n| 種類 | 数値 | 元文 |\n|---|---|---|\n")
            for k, v, s in rm:
                L.append(f"| {k} | **{v}** | {s.replace('|', '｜')[:110]} |\n")

        for k in ("公式_料金", "費用の相場", "一般_データ"):
            sel = d.get(k, [])
            if not sel:
                continue
            nb = [r for r in sel if not r["has_basedate"]]
            L.append(f"\n### {k}（{len(sel)}件・基準日なし {len(nb)}件）— "
                     f"{RULE[k][1]}\n\n")
            for r in sel[:8]:
                L.append(f"- **{r['value']}**"
                         f"{'' if r['has_basedate'] else ' ⚠️基準日なし'}"
                         f" … {r['sentence'][:100]}\n")
            if len(sel) > 8:
                L.append(f"- （ほか {len(sel) - 8}件は NUMBERS.csv）\n")

        if judge:
            L.append("\n### 主語を確かめる数字\n\n")
            for r in judge[:8]:
                L.append(f"- **{r['value']}** … {r['sentence'][:100]}\n")
            if len(judge) > 8:
                L.append(f"- （ほか {len(judge) - 8}件）\n")

    (OUT / "NUMBER_PLAN.md").write_text("".join(L), encoding="utf-8")
    print(f"対象記事 {len(order)}本 → NUMBER_PLAN.md")
    for lv in (1, 2, 3, 4, 5):
        n = [p for p in order if pri(p) == lv]
        if n:
            print(f"  {PRI_NAME[lv]}: {len(n)}本")


if __name__ == "__main__":
    main()
