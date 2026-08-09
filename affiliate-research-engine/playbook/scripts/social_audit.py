#!/usr/bin/env python3
"""
social_audit.py
`social_stock.py` が集めた投稿を、観点ごとに機械で見る。読むだけ。

  python social_audit.py
出力: workspace/social/SOCIAL_QUALITY_AUDIT.md

**判定はするが、1文字も直さない。** 分類は「残せる／要修正／廃棄候補」。

判定の根っこは CLAUDE.md の★最上位ルール。
`workspace/experience_facts.csv` が空なので、**さくら固有の過去の事実は
1つも書けない**。ストックはこの決まりより前に作られている。
"""
import csv
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JST = timezone(timedelta(hours=9))
OUT = ROOT / "workspace/social"
CSV = OUT / "SOCIAL_STOCK_ALL.csv"
FACTS = ROOT / "workspace/experience_facts.csv"

# 台帳に verified の行が1つでもあるか。無ければ一人称の事実は全部アウト
ledger_rows = [r for r in FACTS.read_text(encoding="utf-8").splitlines()
               if r.strip() and not r.startswith("#")
               and not r.startswith("fact_id,")]

# ストックが名乗っている記事タイトルと、**今の**記事タイトル
STALE = {
    "TOEICリスニングが325点で止まっていた私が、聞き流しをやめて2ヶ月で動かした勉強法":
        "TOEICリスニングが止まっているとき、聞き流しを続ける前に確認する3つのこと",
    "現地に短期で行けば一番早い、を27歳の私が費用と時間で調べ直した":
        "「現地が一番早い」を費用と時間で確かめる｜1時間あたりで並べる",
    "オンライン英会話が3日で終わっていた私が、予約をやめて続いた90日":
        "オンライン英会話が続かないのは、話し始めるまでの手数が多いから",
    "セブ島に1ヶ月留学した27歳が、最初の1週間でやめた3つと、残した1つ":
        "セブ島留学の学校を選ぶ4つの確認項目｜コマ数より復習の余白",
    "TOEIC 600点から伸びない社会人が、2年の停滞を抜けた勉強の作り直し方":
        "TOEIC 600点で止まっているとき、勉強法を変える前に確認する4つのこと",
}

# 記事が下書きのまま、または存在しないのに公開URLを貼っているもの
DEAD_LINK = {
    "https://sakura-eigo.com/english-meeting-listening-preparation-tips/":
        "記事583は**まだ下書き**。このURLは開けない",
    "https://example.com/": "**モデルが書いた架空のURL**が残っている",
}

CHECKS = [
    ("未確認の一人称の事実",
     r"4万5000円|45000円|4\.5万|325点|595|600点前後|35万円|32万円|117時間|"
     r"90日続|2ヶ月で動|8コマ|7日中5日|7日のうち5日|3日 4日 2日|3日、4日、2日|"
     r"5年後回し|5年間|27歳|溶かした|2年間ここに留まって|2年動かなかった|"
     r"120コマ|28日|付箋",
     "台帳が空なので、さくら固有の過去は1つも書けない（★最上位ルール）"),
    ("定型の締め",
     r"続きはnoteに書いた|noteに書いた|詳しくはこちら|解説します|"
     r"まとめました|チェックしてみて",
     "「続きはnote」型は生成ルール自身が禁止にしている"),
    ("教訓・説教で締める",
     r"今動かないと|後悔する|やるしかない|変わらない人は",
     "説教で締めない（生成ルールの禁止事項）"),
    ("対比構文",
     r"じゃなかった|ではなく|のほうだ|じゃなくて",
     "1記事2回まで。Threads側は全面禁止"),
    ("抽象語",
     r"手数|設計|構造|物差し|本質|最適化|仕組み化",
     "実際の動作と場面で見せる（禁止語）"),
    ("壊れた出力",
     r"===THREADS_\d===|example\.com|（記事URLを貼る）|（記事URL）",
     "生成の失敗がそのまま残っている"),
    ("句点の混入",
     r"。", "Threadsの型は句点を使わない（改行で切る）"),
    ("ハッシュタグ", r"#\S", "生成ルールで禁止"),
]


def load():
    return list(csv.DictReader(CSV.open(encoding="utf-8")))


def audit(r):
    t = r["text"]
    flags = []
    for name, pat, why in CHECKS:
        if name == "句点の混入" and r["platform"] == "X":
            continue          # Xは句点を使ってよい
        if name == "ハッシュタグ" and "#" not in t:
            continue
        m = re.search(pat, t)
        if m:
            flags.append((name, m.group(0), why))

    # 記事タイトルが古い
    if r["title"] in STALE:
        flags.append(("記事と食い違う", r["title"],
                      f"今の記事名は「{STALE[r['title']]}」。"
                      "投稿が名乗っている体験談は本文から消えている"))

    # 開けないリンク
    for url, why in DEAD_LINK.items():
        if url in t:
            flags.append(("リンクが開けない", url, why))

    # 長さ
    if r["platform"] == "X" and int(r["chars"]) > 90 \
            and not t.startswith("http"):
        flags.append(("Xには長い", f"{r['chars']}字",
                      "x_promo.py の指示は60〜90字"))
    if r["platform"] == "Threads" and r["stock_id"].endswith("-2") \
            and int(r["chars"]) < 120:
        flags.append(("Threadsには薄い", f"{r['chars']}字",
                      "2投稿目は120字以上（threads_builder.review）"))

    # 28字を超える行（Threadsの型）
    if r["platform"] == "Threads" and not t.startswith("http"):
        longs = [l for l in t.split("\n") if len(l) > 28]
        if longs:
            flags.append(("1行が長い", longs[0][:26] + "…",
                          "1行20字前後。28字超は改行で割る"))

    # リンクを押す理由
    if r["platform"] == "Threads" and r["stock_id"].endswith(("-2", "-3")) \
            and r["link"] and r["cta"] == "なし":
        flags.append(("押す理由が無い", "リンクだけ置いている",
                      "何が書いてあるかを1行で予告する"))

    # 重複
    if r["dup_exact"]:
        flags.append(("完全に重複", r["dup_exact"], "同じ文が別の場所にもある"))
    return flags


def verdict(r, flags):
    names = {f[0] for f in flags}
    # 投稿済みは「作り直す」対象ではない。消すか訂正するかは別の判断なので、
    # 下書きと同じ「廃棄候補」に混ぜない
    if r["stock_id"].startswith("TH-LIVE") or r["stock_id"] == "X-LIVE-last":
        if not flags:
            return "残せる（投稿済み）", "引っかかる観点が無い"
        return ("要修正（投稿済み・消すか残すかは別判断）",
                "／".join(sorted(names)) + "。**本文は冒頭しか取れていない**ので、"
                "消すかどうかは全文を見てから決める")
    if "壊れた出力" in names or "リンクが開けない" in names:
        return "廃棄候補", "出力が壊れている。直すより作り直すほうが早い"
    if "未確認の一人称の事実" in names and "記事と食い違う" in names:
        return "廃棄候補", "書けない事実で、しかも記事の中身と別物"
    if "未確認の一人称の事実" in names:
        return "廃棄候補", "台帳に無い、さくら固有の過去を語っている"
    if not flags:
        return "残せる", "引っかかる観点が無い"
    return "要修正", "／".join(sorted(names))


def main():
    rows = load()
    for r in rows:
        r["flags"] = audit(r)
        r["verdict"], r["why"] = verdict(r, r["flags"])

    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    counts = {}
    for r in rows:
        for name, _, _ in r["flags"]:
            counts.setdefault(name, []).append(r["stock_id"])
    verd = {}
    for r in rows:
        verd.setdefault(r["verdict"], []).append(r["stock_id"])

    L = [f"# 投稿ストックの品質監査（{stamp}）\n\n",
         "**判定しただけ。1文字も直していない。**\n\n",
         f"対象 {len(rows)}件（X {sum(1 for r in rows if r['platform']=='X')} / "
         f"Threads {sum(1 for r in rows if r['platform']=='Threads')}）。\n\n",
         "## 判定の前提\n\n",
         f"`workspace/experience_facts.csv` の verified 行は **{len(ledger_rows)}件**。\n"
         "CLAUDE.md の★最上位ルールにより、台帳に無いさくら固有の過去は書けない。\n"
         "**ストックはこの決まり（2026-08-08）より前に作られている。**\n"
         "だから「未確認の一人称の事実」が最多になる。文章の巧拙の話ではない。\n\n",
         "## 分類\n\n| 判定 | 件数 |\n|---|---|\n"]
    for k in ("残せる", "残せる（投稿済み）", "要修正",
              "要修正（投稿済み・消すか残すかは別判断）", "廃棄候補"):
        L.append(f"| {k} | {len(verd.get(k, []))} |\n")
    L.append(f"| **合計** | **{len(rows)}** |\n\n")

    L.append("## 観点ごとの件数\n\n| 観点 | 件数 | 該当 |\n|---|---|---|\n")
    for name, ids in sorted(counts.items(), key=lambda x: -len(x[1])):
        L.append(f"| {name} | {len(ids)} | {' '.join(ids[:6])}"
                 f"{' …' if len(ids) > 6 else ''} |\n")
    L.append(f"\n引っかかりが1つも無かったもの: "
             f"{len([r for r in rows if not r['flags']])}件\n\n")

    L.append("## 1件ずつ\n\n")
    for plat in ("X", "Threads"):
        L.append(f"\n### {plat}\n\n")
        for r in [x for x in rows if x["platform"] == plat]:
            L.append(f"\n#### {r['stock_id']} — **{r['verdict']}**\n\n")
            L.append(f"- 置き場: `{r['file']}`\n")
            L.append(f"- 理由: {r['why']}\n")
            if r["flags"]:
                L.append("\n| 観点 | 原文の該当箇所 | なぜ |\n|---|---|---|\n")
                for n, hit, why in r["flags"]:
                    L.append(f"| {n} | `{hit}` | {why} |\n")
            L.append("\n<details><summary>原文</summary>\n\n```\n"
                     + r["text"] + "\n```\n\n</details>\n")
    (OUT / "SOCIAL_QUALITY_AUDIT.md").write_text("".join(L), encoding="utf-8")

    # CSVへ判定を書き戻す
    fields = list(rows[0].keys())
    for k in ("verdict", "why"):
        if k not in fields:
            fields.append(k)
    fields = [f for f in fields if f != "flags"]
    with CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    for k, v in verd.items():
        print(f"{k}: {len(v)}")
    print(f"→ {OUT}/SOCIAL_QUALITY_AUDIT.md")


if __name__ == "__main__":
    main()
