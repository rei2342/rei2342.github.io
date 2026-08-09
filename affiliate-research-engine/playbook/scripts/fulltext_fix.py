#!/usr/bin/env python3
"""
fulltext_fix.py
既存18本を全文で読み直して見つかった食い違いを直す。

見つかったもの（`workspace/claims/FULLTEXT_18.md` に一覧）:

  232 「開けた日数が7割」が278・277と同じ物差しで、しかもこの記事自身の
      物差し（違いを言葉にできるか）と食い違っていた
  131 締めのリストが「2ヶ月つける」のままで、本文で変えた
      「3問に答え切れた回数を数える」と合っていなかった
  283 見出し「学校を選ぶときに見るところ」の下に、見るところが書いていない
  288 H2がタイトルとほぼ同じ。さらに「25分のうち何分」は
      スパトレのレッスン時間として出典が無い
  526 見出しは「6つの行き先」だが、6つはどこにも出てこない。
      締めのリストは「候補を3つに絞って」で数が合わない
  32  他の17本にある「今日やること」のまとめが無く、CTAの節で終わっていた

  DRY_RUN=false python fulltext_fix.py
出力: workspace/backups/<日付>/fulltext/<id>.json / FULLTEXT_FIX.md
"""
import json
import os
import sys
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

PATCHES = {
    "232": [(
        "<p><strong>確認項目</strong>：2週間、1日1音だけ決めて練習し、"
        "記録をつける。開けた日数が7割を超えるかを見る。届かないなら、"
        "契約の前に置く時間帯を変える。</p>",
        "<p><strong>確認項目</strong>：2週間、1日1音だけ決めて練習する。"
        "毎回、<strong>お手本との違いを言葉にできたかどうか</strong>を記録する。"
        "言葉にできた回のほうが多くなったなら、判定の仕組みは手元にできている。"
        "できない回が続くなら、高い契約の前に、比べる相手を用意するほうが先になる。</p>",
    )],
    "131": [(
        "<li>話す枠を1つ決めて、<strong>2ヶ月つける</strong></li>",
        "<li>面接で聞かれそうな3問に、<strong>答え切れた回数</strong>を2ヶ月記録する</li>",
    )],
    "283": [(
        "<h2>学校を選ぶときに見るところ</h2>",
        "<h2>学校とエージェントを調べる窓口</h2>",
    )],
    "288": [
        ("<h2>予習不要のサービスを選ぶ前に確認したい3つのこと</h2>",
         "<h2>予習を外すと、どこで止まりやすいか</h2>"),
        ("25分のうち何分だったか", "1回のうち何分だったか"),
    ],
    "526": [(
        "<h2>費用と時間を、6つの行き先で並べる</h2>",
        "<h2>費用と時間を、候補ごとに並べる</h2>",
    )],
    # 32だけは足す直し。他の17本にある「今日やること」が無かった
    "32": [(
        "<h2>無料の期間は、判断を安く済ませるために使う</h2>",
        "<h2>今週、4つを順に確認する</h2>\n\n"
        "<ol>\n"
        "<li>結果の<strong>項目別正答率</strong>を見て、低い項目が1か所に"
        "固まっているか散っているかを見る</li>\n"
        "<li>自分のつまずきを<strong>1文で言ってみる</strong>。"
        "言えないなら、内訳の分解に戻る</li>\n"
        "<li>問題集の<strong>詰まる箇所が入れ替わっているか</strong>を見る</li>\n"
        "<li>文字で見れば分かるのに<strong>音になると分からない語</strong>が"
        "あるかを試す</li>\n"
        "</ol>\n\n"
        "<h2>無料の期間は、判断を安く済ませるために使う</h2>"),
    ],
}


def main():
    day = datetime.now(JST).strftime("%Y-%m-%d")
    (BK / day / "fulltext").mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")

    L = [f"# 全文確認で見つかった食い違いを直す {stamp}\n\n",
         f"モード: **{'DRY RUN（書いていない）' if DRY_RUN else 'LIVE（書いた）'}**\n\n",
         "| 記事 | 直したところ | 結果 |\n|---|---|---|\n"]
    for pid, pairs in PATCHES.items():
        g = requests.get(f"{WP}/posts/{pid}", auth=AUTH, headers=UA,
                         params={"context": "edit"}, verify=False, timeout=45)
        if g.status_code != 200:
            L.append(f"| {pid} | — | ❌ 取得できず {g.status_code} |\n")
            continue
        raw = g.json()["content"]["raw"]
        (BK / day / "fulltext" / f"{pid}.json").write_text(
            json.dumps({"id": pid, "checked_at": stamp, "content_raw": raw},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        new, miss = raw, []
        for old, rep in pairs:
            if old not in new:
                miss.append(old[:40])
                continue
            new = new.replace(old, rep, 1)
        if miss:
            L.append(f"| {pid} | — | ❌ 元の文が見つからない: "
                     f"{' / '.join(miss)} |\n")
            print(f"[{pid}] 元の文が見つからない")
            continue
        blockers = _q.generation_blockers(new)
        if blockers:
            L.append(f"| {pid} | — | ❌ ゲートに掛かる: {blockers[0][:60]} |\n")
            print(f"[{pid}] ゲートに掛かるので書かない")
            continue
        res = "（DRY RUN）"
        if not DRY_RUN:
            up = requests.post(f"{WP}/posts/{pid}", auth=AUTH, headers=UA,
                               verify=False, timeout=60, json={"content": new})
            res = "✅" if up.status_code in (200, 201) else \
                f"❌ {up.status_code}"
        L.append(f"| {pid} | {len(pairs)}件 | {res} |\n")
        print(f"[{pid}] {len(pairs)}件 {res}")

    (BK / day / "FULLTEXT_FIX.md").write_text("".join(L), encoding="utf-8")
    print(f"\n→ workspace/backups/{day}/FULLTEXT_FIX.md")


if __name__ == "__main__":
    main()
