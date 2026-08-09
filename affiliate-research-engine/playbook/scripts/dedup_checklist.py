#!/usr/bin/env python3
"""
dedup_checklist.py
**同じ確認項目が複数の記事に出ている**のを、記事ごとの数え方へ分ける。

QUALITY_AUDIT.md に「2ヶ月つけて、開けた日数を数える。7割を超えたら」が
5記事に出ていると書いて、未対応のまま残していた。315は分けたが、
131・288がまだ同じ文だった。読者から見ると使い回しに見えるし、
記事ごとに測るべきものは本当は違う。

  131: 開けた日数 → 面接想定の3問に英語で答え切れた回数
  288: 開けた日数 → 無料期間に声を出した時間の合計

278（コーチング契約前）と277（帰宅後30日）は、開けた日数そのものが
記事の主題なので変えない。

新しいしきい値の数字は作らない。「7割」のような基準を増やすと、
根拠のない数字が1つ増えるだけになる。比べる相手を記事の中に置く。

  DRY_RUN=false python dedup_checklist.py
出力: workspace/backups/<日付>/checklist/<id>.json / DEDUP_CHECKLIST.md
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings()
JST = timezone(timedelta(hours=9))
WP = "https://sakura-eigo.com/wp-json/wp/v2"
AUTH = ("rei.00pt2342@gmail.com", os.environ.get("WP_APP_PASSWORD", ""))
UA = {"User-Agent": "Mozilla/5.0"}
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"
BK = Path("affiliate-research-engine/playbook/workspace/backups")

PATCHES = {
    "131": [(
        "<p><strong>確認項目</strong>：2ヶ月つけて、実際に開けた日数を数える。"
        "7割を超えていれば、渡航後も枠は残りやすい。</p>",
        "<p><strong>確認項目</strong>：2ヶ月のあいだ、上の3問に英語で声に出して"
        "答えるたびに、最後まで言い切れたか、途中で止まったかを記録する。"
        "言い切れた回のほうが多くなったなら、面接で言葉が出ない場面は減らせる。"
        "数えるのは予定を開けた日数ではなく、<strong>答え切れた回数</strong>のほうにする。"
        "面接は、続けた日数ではなく受け答えで判定されるため。</p>",
    )],
    "288": [
        (
            "<p><strong>確認項目</strong>：7日間つけて、予定した日数のうち"
            "何日開けたかを数える。7割を超えていれば、有料に進んでも続きやすい。"
            "届かないなら、置く時間帯を変えてもう一度試す。</p>",
            "<p><strong>確認項目</strong>：無料期間の各回で、"
            "<strong>自分が声に出していた時間</strong>を測って、7日ぶんを合計する。"
            "合計がレッスン1回ぶんの時間に届かないなら、足りないのは受けた回数ではなく"
            "話した量のほうになる。予習を短くするか、置く時間帯を変えて測り直す。</p>",
        ),
        (
            "<li>7日間つけて、<strong>開けた日数</strong>を数える</li>",
            "<li>7日ぶんの声を出した時間を合計して、"
            "<strong>レッスン1回ぶんの時間を超えたか</strong>を見る</li>",
        ),
    ],
}


def main():
    day = datetime.now(JST).strftime("%Y-%m-%d")
    (BK / day / "checklist").mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")

    L = [f"# 確認項目の重複を分ける {stamp}\n\n",
         f"モード: **{'DRY RUN（書いていない）' if DRY_RUN else 'LIVE（書いた）'}**\n\n",
         "278（開けた日数が主題）と277（帰宅後30日が主題）は変えない。\n\n",
         "| 記事 | 置き換え | 結果 |\n|---|---|---|\n"]
    for pid, pairs in PATCHES.items():
        g = requests.get(f"{WP}/posts/{pid}", auth=AUTH, headers=UA,
                         params={"context": "edit"}, verify=False, timeout=45)
        if g.status_code != 200:
            L.append(f"| {pid} | — | ❌ 取得できず {g.status_code} |\n")
            continue
        raw = g.json()["content"]["raw"]
        (BK / day / "checklist" / f"{pid}.json").write_text(
            json.dumps({"id": pid, "checked_at": stamp, "content_raw": raw},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        new = raw
        miss = []
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
        if DRY_RUN:
            L.append(f"| {pid} | {len(pairs)}件 | （DRY RUN） |\n")
            print(f"[{pid}] {len(pairs)}件（DRY RUN）")
            continue
        up = requests.post(f"{WP}/posts/{pid}", auth=AUTH, headers=UA,
                           verify=False, timeout=60, json={"content": new})
        ok = up.status_code in (200, 201)
        L.append(f"| {pid} | {len(pairs)}件 | "
                 f"{'✅' if ok else '❌ ' + str(up.status_code)} |\n")
        print(f"[{pid}] {'OK' if ok else up.status_code}")

    (BK / day / "DEDUP_CHECKLIST.md").write_text("".join(L), encoding="utf-8")
    print(f"\n→ workspace/backups/{day}/DEDUP_CHECKLIST.md")


if __name__ == "__main__":
    main()
