#!/usr/bin/env python3
"""
heading_dedup.py
**同じ見出しが複数の記事に出ている**のを、記事固有の見出しへ直す。

公開49本の H2/H3 を全部集めて数えたら、こうなっていた。

  「合わない人と、先に知っておきたい注意点」 …… 29本
  「この比べ方が向かない場合」 …………………… 2本（37・526）
  「例として、計算の形だけ示す」 ………………… 2本（149・272）

**見出しの下の中身は記事ごとに違う。** テンプレートなのは見出しのほうだけ。
読者は見出しだけを拾って読むので、29本が同じ文字だと「どの記事も同じ」に見える。
中身が名指ししている条件を、そのまま見出しにする。

締めの見出しに「今夜、…」が4本（23・37・131・149）並んでいたのも、
2本を別の言い方へ変えて散らす。

  DRY_RUN=false python heading_dedup.py
出力: workspace/backups/<日付>/headings/<id>.json / HEADING_DEDUP.md
"""
import json
import os
import re
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

OLD = "合わない人と、先に知っておきたい注意点"

# 記事ごとの新しい見出し。**その記事が実際に名指ししている条件**を書く
NEW = {
    "18": "出発月がまだ置けないときと、手数料0円の読み方",
    "19": "入力の列が薄い段階と、直されるのが苦手な場合",
    "27": "絞り込んでも時間が減らない場合",
    "28": "差し引きがプラスの手段が、すでにあるとき",
    "33": "英語の電話がまだ発生していないとき",
    "41": "体力が満タンの日が、週の大半を占めるとき",
    "42": "職務で英語を使う場面が、まだ無いとき",
    "61": "他人に握られた締切が、すでに複数あるとき",
    "64": "毎日の学習が、すでに止まらず回っているとき",
    "67": "目的が滞在中の集中そのものなら、シートは要らない",
    "117": "生活の中に、すでに出番があるとき",
    "136": "行き先とビザの種類が、まだ決まっていないとき",
    "137": "3つの持ち物が、すでに自分の手で回っているとき",
    "138": "頼まれなくても続く習慣が、すでに複数あるとき",
    "150": "1週間以上空いたことが、まだ無いとき",
    "151": "4つの問いを埋めて、独学が回っていると分かったとき",
    "207": "Cの欄が空で、AとBだけになったとき",
    "235": "目的が滞在中の環境そのものなら、右の列は要らない",
    "241": "下の2行が、すでに埋まっているとき",
    "273": "録音が禁止されている場合と、秒数だけを追う危うさ",
    "281": "帰国後に英語を使う場が、最初からあるとき",
    "286": "Q3まで残る練習が、すでに回っているとき",
    "287": "まだ単語が出てこない段階では、回収まで届かない",
    "292": "相手と時間を合わせること自体が、負担になるとき",
    "294": "候補も時期も、まだ広げたい段階のとき",
    "297": "4つの脱落地点の、どこでも止まっていないとき",
    "301": "その場で決められる人に、言い回し集は要らない",
    "305": "行き先も時期も、まだ広げたい段階のとき",
    "546": "同じ講師に、継続して見てもらいたいとき",
}

# 2本ずつ重なっていた見出しと、締めの「今夜、…」の散らし
PAIRS = {
    "37":  [("<h3>この比べ方が向かない場合</h3>",
             "<h3>休職と退職を、金額だけでは比べられない場合</h3>")],
    "526": [("<h3>この比べ方が向かない場合</h3>",
             "<h3>1時間あたりに、そろえられない場合</h3>")],
    "149": [("<h3>例として、計算の形だけ示す</h3>",
             "<h3>例として、3つの箱に数字を入れてみる</h3>"),
            ("<h2>今夜、3つの箱を作る</h2>",
             "<h2>見積もりを取る前に、3つの箱を作る</h2>")],
    "272": [("<h3>例として、計算の形だけ示す</h3>",
             "<h3>例として、4つの箱に数字を入れてみる</h3>")],
    "131": [("<h2>今夜、生活費と話す枠を決める</h2>",
             "<h2>渡航前に、生活費と話す枠を決める</h2>")],
}


def main():
    day = datetime.now(JST).strftime("%Y-%m-%d")
    (BK / day / "headings").mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")

    jobs = {}
    for pid, new in NEW.items():
        jobs.setdefault(pid, []).append(
            (f"<h3>{OLD}</h3>", f"<h3>{new}</h3>"))
    for pid, pairs in PAIRS.items():
        jobs.setdefault(pid, []).extend(pairs)

    L = [f"# 重複していた見出しを記事固有へ直す {stamp}\n\n",
         f"モード: **{'DRY RUN（書いていない）' if DRY_RUN else 'LIVE（書いた）'}**\n\n",
         "見出しの下の中身は記事ごとに違う。テンプレートなのは見出しのほうだけ。\n"
         "中身が名指ししている条件を、そのまま見出しにする。\n\n",
         "| 記事 | 前 | 後 | 結果 |\n|---|---|---|---|\n"]
    ok = ng = 0
    for pid in sorted(jobs, key=int):
        g = requests.get(f"{WP}/posts/{pid}", auth=AUTH, headers=UA,
                         params={"context": "edit"}, verify=False, timeout=45)
        if g.status_code != 200:
            L.append(f"| {pid} | — | — | ❌ 取得できず {g.status_code} |\n")
            ng += 1
            continue
        raw = g.json()["content"]["raw"]
        (BK / day / "headings" / f"{pid}.json").write_text(
            json.dumps({"id": pid, "checked_at": stamp, "content_raw": raw},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        new_html, rows, miss = raw, [], []
        for old, rep in jobs[pid]:
            if old not in new_html:
                miss.append(old)
                continue
            new_html = new_html.replace(old, rep, 1)
            rows.append((_q.strip_tags(old), _q.strip_tags(rep)))
        if miss:
            for m in miss:
                L.append(f"| {pid} | {_q.strip_tags(m)} | — | "
                         f"❌ 元の見出しが見つからない |\n")
            ng += 1
            continue
        # 書く前に公開ゲートへ通す
        blockers = _q.generation_blockers(new_html)
        if blockers:
            L.append(f"| {pid} | — | — | ❌ ゲートに掛かる: "
                     f"{blockers[0][:60]} |\n")
            ng += 1
            continue
        res = "（DRY RUN）"
        if not DRY_RUN:
            up = requests.post(f"{WP}/posts/{pid}", auth=AUTH, headers=UA,
                               verify=False, timeout=60,
                               json={"content": new_html})
            res = "✅" if up.status_code in (200, 201) else \
                f"❌ {up.status_code}"
        for a, b in rows:
            L.append(f"| {pid} | {a} | {b} | {res} |\n")
        ok += 1
        print(f"[{pid}] {len(rows)}件 {res}")

    L.append(f"\n直した記事 **{ok}本** / 直せなかった記事 {ng}本\n")
    (BK / day / "HEADING_DEDUP.md").write_text("".join(L), encoding="utf-8")
    print(f"\n{ok}本 → workspace/backups/{day}/HEADING_DEDUP.md")


if __name__ == "__main__":
    main()
