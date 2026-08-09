#!/usr/bin/env python3
"""
cta_optimize.py
CTAを記事ごとに最適化する。「一律2本」をやめる。

**報酬単価では決めない。** その記事を読み終えた人の次の行動が
案件に繋がるかどうかで決める。

  CTAなし … 共感・入口／意味を考える／制度の概要／サービス選択にまだ進んでいない／
            本文で案件の必要性を説明できない
  1本 …… 費用試算／学習法の診断／サービスの選び方／条件と案件が1対1
  2本 …… 本文で**別々の役割として説明できている**ときだけ
          （発音矯正と会話量／独学支援と人の指導／学校比較とエージェント相談）

本文のCTAは2つの形がある。両方に対応する。
  箱型 … <hr> + <div style="background:#f9f9f9…"> の中に <p><a> が並ぶ
  地の文型 … <p><strong>公式情報</strong>…</p> の直後に <p><a> が1本

**アフィリエイトURLは書き換えない。** 残すものはそのまま、外すものは丸ごと消す。

  DRY_RUN=false python cta_optimize.py
出力: workspace/backups/<日付>/cta/<id>.json / CTA_OPTIMIZE.md / .csv
"""
import csv
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings()
sys.path.insert(0, str(Path(__file__).parent))
import quality_rules as _q

JST = timezone(timedelta(hours=9))
WP = "https://sakura-eigo.com/wp-json/wp/v2"
AUTH = ("rei.00pt2342@gmail.com", os.environ.get("WP_APP_PASSWORD", ""))
UA = {"User-Agent": "Mozilla/5.0"}
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"
BK = Path("affiliate-research-engine/playbook/workspace/backups")

# URLの断片 → 案件名
PROGRAM = [
    ("a_id=5640991", "speek"), ("a_id=5640986", "フィリピン留学ナビ"),
    ("a_id=5640988", "U-GAKU"), ("a_id=5640990", "留学情報館"),
    ("a_id=5640987", "CEBRIDGE"), ("a_id=5640981", "スパトレ"),
    ("a_id=5640982", "DMM英会話"),
    ("4B9W9D+27S3UA", "ネイティブキャンプ留学"),
    ("4B9W9D+2IHWQA", "QQ English"),
    ("4B9W9D+28DJG2", "ネイティブキャンプ"),
    ("4B9W9D+1LR2GI", "レアジョブ英会話"),
    ("4B9W9D+2OG8S2", "スタディサプリ 新日常英会話"),
    ("4B9W9D+28YZ1U", "スタディサプリ セットプラン"),
    ("4B9YLD+EAFAQ", "Notta"), ("4B9YLD+2HB1IQ", "Notta Memo"),
]

# 記事ごとの決定。keep が空ならCTAなし
DECISION = {
    # ── CTAなし（15本）──────────────────────────────
    "27":  ([], "学習時間を自分の用途で割り直す記事。結論は計算手順で、"
                "留学エージェントのCTAは本文のどこからも必要性を説明できない"),
    "28":  ([], "上達しない8つの理由を1本の鎖に並べ直す整理記事。"
                "読者はまだどのサービスを選ぶかの段階に来ていない"),
    "41":  ([], "体力が枯れた日の最低ラインを決める共感・入口記事。"
                "決めるのは自分の枠であって、サービスではない"),
    "61":  ([], "やる気ではなく締切の本数を数える共感・入口記事。"
                "結論は表を埋めることで、次の行動に案件が入らない"),
    "64":  ([], "コーチング契約前の12の質問。CTAは留学エージェント2本で、"
                "記事の主題と案件が噛み合っていない"),
    "117": ([], "ゼロから始める人向けの共感・入口記事。"
                "今日やった分に明日の出番を付けるところまでが結論"),
    "136": ([], "移住の入口条件を整理する制度の概要記事。"
                "行き先とビザが決まる前なので、相談で決められることが少ない"),
    "137": ([], "コーチングの体験談の読み分け方。CTAは留学エージェント2本で、"
                "記事の主題と案件が噛み合っていない"),
    "150": ([], "空いた日から戻る手順を決める共感・入口記事"),
    "151": ([], "「意味ない」を自分の条件へ翻訳する4問。意味を考える記事で、"
                "4問を埋めた結果が「契約は要らない」になることもある"),
    "207": ([], "不安を調べる・試す・残るの3つに仕分ける整理記事。"
                "本文が「Cの欄が空なら相談はまだ早い」と書いている"),
    "238": ([], "ワーホリに間に合うかを2つの締切に分ける制度の概要記事"),
    "289": ([], "30代の移住が遅いかを締切の有無で考える共感・入口記事"),
    "292": ([], "独学が3日で止まる人向けの共感・入口記事。"
                "教材を買う前に確認する3つ、が結論"),
    "301": ([], "エージェントに勧められたときの言い回し集。"
                "紹介料の偏りに備える記事の末尾に、エージェントのCTAを置かない"),

    # ── 2本を残す（6本）。本文で別々の役割を説明できている ────
    "32":  (["speek", "スパトレ"],
            "確認4「音の練習が抜けていないか」が発音矯正、"
            "締めの「無料の期間」が会話量。役割が違う"),
    "283": (["スパトレ", "フィリピン留学ナビ"],
            "出発前の事前学習と、現地の学校選び。時期も相手も違う"),
    "304": (["speek", "スパトレ"],
            "確認3の録音が発音矯正、確認4の「使う場面」が会話量"),
    "310": (["speek", "スパトレ"],
            "「発音そのものを見てもらう」と「人とやりとりする回数を増やす」を"
            "H3で分けて説明している"),
    "315": (["スパトレ", "フィリピン留学ナビ"],
            "帰国後に続ける形と、現地の学校選び"),
    "521": (["speek", "スパトレ"],
            "確認3が発音の直し方、締めが話す練習。扱う範囲が違う"),

    # ── 1本（28本）────────────────────────────────
    "18":  (["留学情報館"], "エージェント比較の記事。相談窓口が次の行動と1対1"),
    "19":  (["スパトレ"], "入力・出力・矯正のうち矯正を外に出す文脈。"
                          "アプリ側（スタディサプリ）は入力寄りで役割が重なる"),
    "23":  (["ネイティブキャンプ留学"], "3つの箱の①を見積もりで確定させる。"
                                        "留学情報館は同じエージェントで役割が重なる"),
    "33":  (["ネイティブキャンプ"], "職務10場面を毎日使う文脈。"
                                    "QQ Englishはカランメソッドで役割が違う"),
    "37":  (["ネイティブキャンプ留学"], "休職と退職の比較。①の実費を見積もりで確定させる"),
    "40":  (["留学情報館"], "手数料の仕組みを理解した上での相談。もともと1本"),
    "42":  (["ネイティブキャンプ"], "使う十数文を毎日回す文脈"),
    "67":  (["フィリピン留学ナビ"], "フィリピン留学の申し込み前。専門エージェントが1対1"),
    "131": (["留学情報館"], "目標額を上げるか出発を早めるかの相談。"
                            "ネイティブキャンプ留学は同じ役割で重なる"),
    "138": (["スパトレ"], "総額を残った月数で割る記事。"
                          "高額契約の前に安い枠で試す、が次の行動"),
    "149": (["留学情報館"], "3つの箱を埋めてから相談に行く、が本文の結論"),
    "232": (["speek"], "発音の判定の仕組みを外に置く。もともと1本"),
    "235": (["フィリピン留学ナビ"], "セブ島留学1ヶ月の比較表。専門エージェントが1対1"),
    "241": (["スパトレ"], "反応が返る2つの工程を外に出す。相手が人であることが条件"),
    "272": (["留学情報館"], "行ける月を決めてから相談に行く、が本文の結論"),
    "273": (["ネイティブキャンプ"], "話した秒数を測る。回数無制限が測定の前提と噛み合う"),
    "277": (["スパトレ"], "帰宅後30日の枠。もともと1本"),
    "278": (["スパトレ"], "卒業後の形を安い枠で試す。もともと1本"),
    "281": (["DMM英会話"], "帰国後の出口を作る文脈。speekは発音で、この記事の主題ではない"),
    "282": (["スパトレ"], "話す量を測る。もともと1本"),
    "286": (["ネイティブキャンプ"], "「反応が返るか」の3問判定。相手が人であることが条件"),
    "287": (["ネイティブキャンプ"], "詰まりの回収を数える。回数無制限が前提と噛み合う"),
    "288": (["スパトレ"], "スパトレの評判を扱う個別サービス記事。もともと1本"),
    "294": (["留学情報館"], "決め方を決めてから相談に行く"),
    "297": (["ネイティブキャンプ"], "脱落地点が予約なら、予約不要の形が1対1で対応する。"
                                    "DMM英会話は同じオンライン英会話で役割が重なる"),
    "305": (["ネイティブキャンプ留学"], "ワーホリの渡航初日を想定した準備"),
    "526": (["フィリピン留学ナビ"], "行き先ごとの時間と費用を埋めるには学校の情報が要る"),
    "546": (["ネイティブキャンプ"], "話し始めるまでの手数。もともと1本"),
}

# 2本を残す記事で、CTAの直前に置く「役割の違い」の説明
ROLE_NOTE = {
    "32": "この2つは役割が違う。<strong>speekは発音の直し方</strong>を扱い、"
          "<strong>スパトレは話す量</strong>を扱う。いま足りていないほうを選ぶ。",
    "283": "この2つは時期が違う。<strong>スパトレは出発前の事前学習</strong>、"
           "<strong>フィリピン留学ナビは現地の学校選び</strong>になる。",
    "304": "この2つは扱う範囲が違う。<strong>speekは音の直し方</strong>、"
           "<strong>スパトレは覚えた語を使う場面</strong>を作る。",
    "310": "",   # 本文のH3ですでに分けて説明している
    "315": "この2つは時期が違う。<strong>スパトレは帰国後に続ける形</strong>、"
           "<strong>フィリピン留学ナビは現地の学校選び</strong>になる。",
    "521": "この2つは扱う範囲が違う。<strong>speekは音の直し方</strong>、"
           "<strong>スパトレは話す練習の量</strong>になる。",
}

BOX_RE = re.compile(
    r'\n?<hr>\s*<div style="background:#f9f9f9[^"]*"[^>]*>.*?</div>',
    re.DOTALL)
NOTE_MARK = "<!-- cta-role-note -->"


def program_of(href):
    h = href.replace("&#038;", "&").replace("&amp;", "&")
    return next((n for k, n in PROGRAM if k in h), None)


def strip_cta(raw, keep):
    """残す案件以外のCTAを消す。URLは書き換えない。"""
    out, removed = raw, []

    # ① 箱型
    m = BOX_RE.search(out)
    if m:
        box = m.group(0)
        paras = re.findall(r'<p\b[^>]*>.*?</p>', box, re.DOTALL)
        drop = []
        for p in paras:
            a = re.search(r'href="([^"]+)"', p)
            if not a:
                continue
            name = program_of(a.group(1))
            if name and name not in keep:
                drop.append((p, name))
        if len([p for p in paras
                if (a := re.search(r'href="([^"]+)"', p))
                and program_of(a.group(1))]) == len(drop) and drop:
            # 残るCTAが無い。箱ごと外す。PR表記は別に足すので後段で確認
            out = out.replace(box, "")
            removed += [n for _, n in drop]
        else:
            newbox = box
            for p, n in drop:
                newbox = newbox.replace(p + "\n", "").replace(p, "")
                removed.append(n)
            out = out.replace(box, newbox)

    # ② 地の文型。公式情報の段落とCTAの段落をセットで外す
    for m in list(re.finditer(
            r'(?:<p><strong>公式情報</strong>[^\n]*?</p>\s*\n?)?'
            r'<p><a\b[^>]*href="([^"]+)"[^>]*>.*?</a>[^<]*</p>',
            out, re.DOTALL)):
        name = program_of(m.group(1))
        if not name or name in keep:
            continue
        out = out.replace(m.group(0), "", 1)
        removed.append(name)

    out = re.sub(r"\n{3,}", "\n\n", out)
    return out, removed


def ensure_pr(html):
    """PR表記を必ず残す。箱ごと外した記事で消えることがある。"""
    if "アフィリエイトリンク" in html:
        return html
    return html.rstrip() + \
        "\n\n<p>※本記事にはアフィリエイトリンクが含まれます（PR）</p>"


def main():
    day = datetime.now(JST).strftime("%Y-%m-%d")
    (BK / day / "cta").mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")

    rows = []
    for pid in sorted(DECISION, key=int):
        keep, reason = DECISION[pid]
        g = requests.get(f"{WP}/posts/{pid}", auth=AUTH, headers=UA,
                         params={"context": "edit"}, verify=False, timeout=45)
        if g.status_code != 200:
            rows.append({"post_id": pid, "before": "", "after": "",
                         "kept": "", "removed": "", "reason": reason,
                         "result": f"取得できず {g.status_code}"})
            continue
        raw = g.json()["content"]["raw"]
        (BK / day / "cta" / f"{pid}.json").write_text(
            json.dumps({"id": pid, "checked_at": stamp, "content_raw": raw},
                       ensure_ascii=False, indent=2), encoding="utf-8")

        before = [program_of(h) for h in
                  re.findall(r'<a\b[^>]*href="([^"]+)"', raw)]
        before = [b for b in before if b]

        new, removed = strip_cta(raw, keep)

        # 2本残す記事に、役割の違いの説明を1文入れる
        note = ROLE_NOTE.get(pid, "")
        if len(keep) == 2 and note and NOTE_MARK not in new:
            m = BOX_RE.search(new)
            if m:
                new = new.replace(
                    m.group(0),
                    f"\n{NOTE_MARK}\n<p>{note}</p>" + m.group(0), 1)
            else:
                fa = re.search(r'<p><a\b[^>]*href="[^"]*'
                               r'(?:moshimo|a8\.net)[^"]*"', new)
                if fa:
                    new = (new[:fa.start()] + f"{NOTE_MARK}\n<p>{note}</p>\n"
                           + new[fa.start():])

        new = ensure_pr(new)
        after = [program_of(h) for h in
                 re.findall(r'<a\b[^>]*href="([^"]+)"', new)]
        after = [a for a in after if a]

        if sorted(after) != sorted(keep):
            rows.append({"post_id": pid, "before": " + ".join(before),
                         "after": " + ".join(after), "kept": " + ".join(keep),
                         "removed": " + ".join(removed), "reason": reason,
                         "result": "❌ 残った案件が想定と違う"})
            print(f"[{pid}] 想定 {keep} / 実際 {after}")
            continue

        blockers = _q.generation_blockers(new)
        if blockers:
            rows.append({"post_id": pid, "before": " + ".join(before),
                         "after": " + ".join(after), "kept": " + ".join(keep),
                         "removed": " + ".join(removed), "reason": reason,
                         "result": f"❌ ゲート: {blockers[0][:50]}"})
            print(f"[{pid}] ゲートに掛かる")
            continue

        res = "（DRY RUN）"
        if not DRY_RUN and new != raw:
            up = requests.post(f"{WP}/posts/{pid}", auth=AUTH, headers=UA,
                               verify=False, timeout=60, json={"content": new})
            res = "✅" if up.status_code in (200, 201) else \
                f"❌ {up.status_code}"
        elif new == raw:
            res = "変更なし"
        rows.append({"post_id": pid, "before": " + ".join(before),
                     "after": " + ".join(after) or "（CTAなし）",
                     "kept": " + ".join(keep) or "（なし）",
                     "removed": " + ".join(removed) or "（なし）",
                     "reason": reason, "result": res})
        print(f"[{pid}] {len(before)}本 → {len(after)}本 {res}")

    total_after = sum(len(r["after"].split(" + ")) if r["after"]
                      and r["after"] != "（CTAなし）" else 0 for r in rows)
    none_n = sum(1 for r in rows if r["after"] == "（CTAなし）")
    one_n = sum(1 for r in rows if r["after"] and r["after"] != "（CTAなし）"
                and " + " not in r["after"])
    two_n = sum(1 for r in rows if " + " in r["after"])
    byprog = Counter()
    for r in rows:
        if r["after"] and r["after"] != "（CTAなし）":
            for p in r["after"].split(" + "):
                byprog[p] += 1

    L = [f"# CTAを記事ごとに最適化 {stamp}\n\n",
         f"モード: **{'DRY RUN（書いていない）' if DRY_RUN else 'LIVE（書いた）'}**\n\n",
         "報酬単価では決めていない。**その記事を読み終えた人の次の行動**が\n"
         "案件に繋がるかどうかで決めた。\n\n",
         "| 区分 | 本数 |\n|---|---|\n",
         f"| CTAなし | **{none_n}** |\n| CTA1本 | **{one_n}** |\n"
         f"| CTA2本 | **{two_n}** |\n| CTA総数 | **{total_after}** |\n\n",
         "## 案件別の本数\n\n| 案件 | 本数 |\n|---|---|\n"]
    for p, n in byprog.most_common():
        L.append(f"| {p} | {n} |\n")
    L.append("\n## 記事ごと\n\n| 記事 | 前 | 後 | 外した案件 | 理由 | 結果 |\n"
             "|---|---|---|---|---|---|\n")
    for r in rows:
        L.append(f"| {r['post_id']} | {r['before']} | {r['after']} | "
                 f"{r['removed']} | {r['reason']} | {r['result']} |\n")

    (BK / day / "CTA_OPTIMIZE.md").write_text("".join(L), encoding="utf-8")
    with open(BK / day / "CTA_OPTIMIZE.csv", "w", encoding="utf-8",
              newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nCTAなし{none_n} / 1本{one_n} / 2本{two_n} / 総数{total_after}")
    print(f"→ workspace/backups/{day}/CTA_OPTIMIZE.md")


if __name__ == "__main__":
    main()
