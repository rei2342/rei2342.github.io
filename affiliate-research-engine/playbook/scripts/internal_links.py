#!/usr/bin/env python3
"""
internal_links.py
49本を役割で分類して、内部リンクを設計・反映する。

**監査を通った公開記事だけ**を対象にする。下書き（Callan記事など）は入れない。

設計の考え方:
  共感・入口 → 判断基準・勉強法 → 比較・選び方 → 個別サービス → CTA
  留学系:     費用・条件 → 国・期間 → 学校/エージェントの選び方 → 個別 → 相談
  TOEIC系:    スコア帯・停滞 → パート別の切り分け → 学習法 → 発音・発話 → サービス

反映のルール:
  - アンカーだけでリンク先が分かる（「こちら」「詳しく」は使わない）
  - 同じ記事へ2回リンクしない
  - 1記事2〜4本を目安。要らないなら減らす
  - ハブには子記事の一覧、子からはハブへ戻す

  DRY_RUN=false python internal_links.py
出力: workspace/seo/INTERNAL_LINKS.md / backups/<日付>/links/<id>.json
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
import wp_audit as _wa

OUT = Path("affiliate-research-engine/playbook/workspace/seo")
BK = Path("affiliate-research-engine/playbook/workspace/backups")
JST = timezone(timedelta(hours=9))
WP = "https://sakura-eigo.com/wp-json/wp/v2"
AUTH = ("rei.00pt2342@gmail.com", os.environ.get("WP_APP_PASSWORD", ""))
UA = {"User-Agent": "Mozilla/5.0"}
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"

# ── 役割の分類 ────────────────────────────────────────────
# hub  : そのテーマの入口。子記事の一覧を持つ
# child: 個別の判断材料
ROLE = {
    # ===== 学習の継続・入口 =====
    "19":  ("hub",   "学習法", "英語の独学が実らないのは、入力・出力・矯正のどれかが0だから"),
    "292": ("child", "学習法", "独学が3日で止まる人の確認項目"),
    "41":  ("child", "学習法", "体力が枯れた日の最低ラインの決め方"),
    "150": ("child", "学習法", "空いた日から戻る復帰手順"),
    "117": ("child", "学習法", "今日やった分に明日の出番を1つ付ける"),
    "61":  ("child", "学習法", "他人に握られた締切の作り方"),
    "27":  ("child", "学習法", "必要な学習時間を自分の用途で計算し直す"),
    "286": ("child", "学習法", "反応が返るかで3問だけ判定する"),
    "28":  ("child", "学習法", "上達しない8つの理由を1本の鎖に並べ直す"),
    "310": ("child", "学習法", "無料・低価格アプリで足りる人と足りない人"),
    "232": ("child", "発音",   "大人の発音は直らないのかを確認する"),

    # ===== オンライン英会話 =====
    "546": ("hub",   "英会話", "オンライン英会話が続かないのは、話し始めるまでの手数"),
    "297": ("child", "英会話", "4つの脱落地点のどこで止まるか"),
    "287": ("child", "英会話", "出席ではなく回収の数で測る"),
    "273": ("child", "英会話", "1回のレッスンで話した秒数を測る"),
    "288": ("child", "英会話", "予習が要るサービスを選ぶ前の確認"),

    # ===== 仕事の英語 =====
    "42":  ("hub",   "仕事",   "仕事の英語で使う十数文を数える"),
    "33":  ("child", "仕事",   "職務10場面を頻度順に並べて上位3つを固める"),

    # ===== TOEIC =====
    "304": ("hub",   "TOEIC",  "TOEIC 600点で止まっているときの確認項目"),
    "32":  ("child", "TOEIC",  "TOEIC500点から上げる勉強法"),
    "521": ("child", "TOEIC",  "TOEICリスニングが止まっているときの切り分け"),
    "282": ("child", "TOEIC",  "TOEIC400点台でワーホリに行く前の確認"),

    # ===== コーチング =====
    "278": ("hub",   "コーチング", "英語コーチングに払う前に確認する3つのこと"),
    "64":  ("child", "コーチング", "契約前に投げる12の質問"),
    "137": ("child", "コーチング", "体験談を到達点か傾きかで読み分ける"),
    "138": ("child", "コーチング", "総額を残った月数で割って単価にする"),
    "151": ("child", "コーチング", "「意味ない」を自分の条件へ翻訳する4問"),
    "241": ("child", "コーチング", "独学の工程を切り分けて反応だけ外に出す"),

    # ===== 留学の費用 =====
    "23":  ("hub",   "費用",   "ワーホリの貯金はいくら必要か"),
    "149": ("child", "費用",   "カナダ ワーホリの費用を3つの箱で出す"),
    "272": ("child", "費用",   "フィリピン留学の費用を社会人が計算する"),
    "37":  ("child", "費用",   "半年の留学にいくらかかるか（休職と退職の比較）"),
    "131": ("child", "費用",   "収入が始まるまでの月数を決める"),
    "526": ("child", "費用",   "「現地が一番早い」を1時間あたりで並べる"),

    # ===== 留学・ワーホリの判断 =====
    "289": ("hub",   "留学判断", "30代の海外移住が遅いかは締切の有無で決まる"),
    "238": ("child", "留学判断", "ワーホリに間に合うかの2つの締切"),
    "294": ("child", "留学判断", "留学の比較が終わらないときの決め方"),
    "207": ("child", "留学判断", "留学の不安を3つに仕分ける"),
    "136": ("child", "留学判断", "「英語できなくても移住できる」の段階"),
    "18":  ("child", "留学判断", "留学エージェントの比較が終わらないとき"),
    "305": ("child", "留学判断", "ワーホリに要る英語を渡航初日の5場面で測る"),

    # ===== 学校・エージェントの選び方 =====
    "315": ("hub",   "学校選び", "セブ島留学の学校を選ぶ4つの確認項目"),
    "235": ("child", "学校選び", "セブ島留学1ヶ月の比較表に帰国後の列を足す"),
    "67":  ("child", "学校選び", "申し込む前に帰国後4週間の予定を埋める"),
    "283": ("child", "学校選び", "セブ島留学に初心者で行く前の確認"),
    "277": ("child", "学校選び", "国内留学・英語合宿を申し込む前に"),
    "281": ("child", "学校選び", "帰国後に落ちやすい能力の順番"),
    "40":  ("child", "エージェント", "無料エージェントの手数料の仕組みと3つの質問"),
    "301": ("child", "エージェント", "勧められたときに使う言い回し集"),
}

# ── 導線。from → [to, ...] ────────────────────────────
# 「読者が次に知りたいこと」の順で並べる。収益記事へ集中させない
FLOW = {
    # 学習法クラスタ
    # 241はカニバリ候補（どの工程を外に出すか）。役割の違いを添えて双方向にする
    "19":  ["292", "286", "241", "310"],
    "292": ["19", "41", "150"],
    "41":  ["19", "150"],
    "150": ["41", "117"],
    "117": ["19", "61"],
    "61":  ["117", "27"],
    "27":  ["19", "136"],
    "286": ["19", "28", "232"],
    "28":  ["546", "19"],
    "310": ["19", "288"],
    "232": ["286", "288"],
    # 英会話クラスタ
    "546": ["297", "273", "288"],
    "297": ["546", "287"],
    "287": ["546", "273"],
    "273": ["546", "287"],
    "288": ["546", "310"],
    # 仕事
    "42":  ["33", "546"],
    "33":  ["42", "273"],
    # TOEIC
    "304": ["521", "32", "282"],
    "32":  ["304", "521"],
    "521": ["304", "273"],
    "282": ["304", "305"],
    # コーチング
    "278": ["64", "138", "137"],
    "64":  ["278", "137"],
    "137": ["278", "138"],
    "138": ["278", "64"],
    "151": ["278", "241"],
    "241": ["151", "19"],
    # 費用
    "23":  ["149", "131", "37"],
    "149": ["23", "131"],
    "272": ["23", "315"],
    "37":  ["23", "131"],
    "131": ["23", "149"],
    "526": ["23", "272"],
    # 留学判断
    "289": ["238", "294", "23", "207"],
    "238": ["289", "23"],
    "294": ["289", "18"],
    "207": ["289", "294"],
    "136": ["289", "305"],
    "18":  ["294", "40"],
    "305": ["136", "315"],
    # 学校選び
    "315": ["235", "283", "67", "277"],
    "235": ["315", "67"],
    "67":  ["315", "281"],
    "283": ["315", "305"],
    "277": ["315", "526"],
    "281": ["67", "546"],
    "40":  ["301", "18"],
    "301": ["40", "294"],
}

# ── 記事の種類 ────────────────────────────────────────
# ROLE は「ハブか子か」だけを持つ。読者の移動を設計するには、
# **記事が読者のどの段階に置かれるか**が要る。それをここで分ける。
#   entry    共感・入口（悩みや不安の言葉で検索される）
#   criteria 判断基準・勉強法（何を見て決めるか）
#   compare  比較・選び方（複数の候補を並べる）
#   money    費用・条件（金額と制度）
#   service  個別サービス（特定の案件を主題にする）
KIND = {
    "19": "criteria", "292": "entry", "41": "entry", "150": "entry",
    "117": "entry", "61": "entry", "27": "criteria", "286": "criteria",
    "28": "criteria", "310": "compare", "232": "entry",
    "546": "entry", "297": "entry", "287": "criteria", "273": "criteria",
    "288": "service",
    "42": "criteria", "33": "criteria",
    "304": "criteria", "32": "criteria", "521": "criteria",
    "282": "criteria",
    "278": "criteria", "64": "compare", "137": "criteria",
    "138": "criteria", "151": "entry", "241": "criteria",
    "23": "money", "149": "money", "272": "money", "37": "money",
    "131": "money", "526": "compare",
    "289": "entry", "238": "criteria", "294": "compare", "207": "entry",
    "136": "entry", "18": "compare", "305": "criteria",
    "315": "compare", "235": "compare", "67": "criteria",
    "283": "criteria", "277": "compare", "281": "criteria",
    "40": "compare", "301": "criteria",
}

# ── カニバリ候補 ──────────────────────────────────────
# 検索意図が重なる組。**統合はしない。**
# どちらも要る理由が読者に分かるよう、リンクの文言に観点を添える。
# （2026-08-09に本文を読み比べて選んだ。タイトルの語の重なりだけでは出ない）
CANNIBAL = {
    ("546", "297"): "どこで止まるかを4か所に分ける観点",
    ("19", "241"): "どの工程を外に出すかという観点",
    ("18", "294"): "決め方そのものを先に決める観点",
    ("67", "281"): "落ちやすさの順番という観点",
}


def cannibal_note(a, b):
    return CANNIBAL.get((a, b)) or CANNIBAL.get((b, a)) or ""


MARK_START = "<!-- internal-links:START -->"
MARK_END = "<!-- internal-links:END -->"
BLOCK_RE = re.compile(
    re.escape(MARK_START) + r".*?" + re.escape(MARK_END), re.DOTALL)


def main():
    day = datetime.now(JST).strftime("%Y-%m-%d")
    (BK / day / "links").mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")

    posts = {str(p["id"]): p for p in _wa.published()}
    print(f"公開記事 {len(posts)}本")

    # 監査を通った公開記事だけを対象にする
    ok = {}
    for pid, p in posts.items():
        html = p.get("content", {}).get("rendered", "")
        if _q.generation_blockers(html):
            print(f"[{pid}] ブロッカーあり。リンク対象から外す")
            continue
        ok[pid] = p

    L = [f"# 内部リンクの設計と反映 {stamp}\n\n",
         f"モード: **{'DRY RUN（書いていない）' if DRY_RUN else 'LIVE（書いた）'}**\n\n",
         f"対象: 監査を通った公開記事 **{len(ok)}本**。下書きは含めない。\n\n"]

    # 役割の一覧
    L.append("## 役割の分類\n\n| クラスタ | ハブ | 子記事 |\n|---|---|---|\n")
    clusters = {}
    for pid, (role, cl, _) in ROLE.items():
        clusters.setdefault(cl, {"hub": [], "child": []})[role].append(pid)
    for cl, d in clusters.items():
        L.append(f"| {cl} | {' '.join(d['hub']) or '—'} | "
                 f"{' '.join(d['child']) or '—'} |\n")

    # 記事の種類
    L.append("\n## 記事の種類\n\n| 種類 | 本数 | 記事 |\n|---|---|---|\n")
    LABEL = {"entry": "共感・入口", "criteria": "判断基準・勉強法",
             "compare": "比較・選び方", "money": "費用・条件",
             "service": "個別サービス"}
    by_kind = {}
    for pid, k in KIND.items():
        by_kind.setdefault(k, []).append(pid)
    for k, lab in LABEL.items():
        v = sorted(by_kind.get(k, []), key=int)
        L.append(f"| {lab} | {len(v)} | {' '.join(v)} |\n")
    hubs = sorted((p for p, r in ROLE.items() if r[0] == "hub"), key=int)
    L.append(f"| ハブ（上の分類と重なる） | {len(hubs)} | {' '.join(hubs)} |\n")

    L.append("\n## カニバリ候補\n\n"
             "検索意図が重なる組。**統合はしない。**\n"
             "どちらも要る理由が分かるよう、リンクの文言に観点を添える。\n\n"
             "| A | B | 添える観点 |\n|---|---|---|\n")
    for (a, b), note in CANNIBAL.items():
        L.append(f"| {a} {ROLE[a][2][:26]} | {b} {ROLE[b][2][:26]} | {note} |\n")

    L.append("\n## 反映\n\n| 記事 | 種類 | リンク先 | 結果 |\n|---|---|---|---|\n")
    applied = 0
    url_of = {p: ok[p]["link"].rstrip("/") for p in ok}
    id_of = {v: k for k, v in url_of.items()}
    for pid in sorted(FLOW, key=int):
        if pid not in ok:
            L.append(f"| {pid} | — | — | 対象外（未公開かブロッカーあり） |\n")
            continue

        g = requests.get(f"{WP}/posts/{pid}", auth=AUTH, headers=UA,
                         params={"context": "edit"}, verify=False, timeout=45)
        if g.status_code != 200:
            L.append(f"| {pid} | — | — | ❌ 取得できず {g.status_code} |\n")
            continue
        raw = g.json()["content"]["raw"]
        (BK / day / "links" / f"{pid}.json").write_text(
            json.dumps({"id": pid, "checked_at": stamp, "content_raw": raw},
                       ensure_ascii=False, indent=2), encoding="utf-8")

        # **本文の地の文がすでにリンクしている先は、一覧に入れない。**
        # 入れると同じ記事へ2回リンクすることになる。
        # 反映1回目はここを見ておらず、13本で重複していた（2026-08-09に修正）
        prose = BLOCK_RE.sub(" ", raw)
        already = {id_of[u.rstrip("/")]
                   for u in re.findall(
                       r'href="(https://sakura-eigo\.com[^"]*)"', prose)
                   if u.rstrip("/") in id_of}

        # 設計した導線 → 同じクラスタの兄弟、の順に埋める
        role = ROLE.get(pid, ("child", "", ""))[0]
        cluster = ROLE.get(pid, (None, "", ""))[1]
        siblings = [p for p in sorted(ROLE, key=int)
                    if ROLE[p][1] == cluster and p != pid]
        cand = list(FLOW[pid]) + siblings

        # **1記事あたり4本を上限にする。**
        # 地の文にすでに4本あるなら、一覧は足さない（要らないなら減らす）。
        # ハブだけは例外で、子記事の一覧を必ず持たせる
        designed = max(2, min(4, len(FLOW[pid])))
        if role == "hub":
            want = designed
        else:
            # 設計した本数を上限にする。**足りない分を埋めに行かない。**
            # そのうえで、地の文と合わせて4本を超えないところまで削る
            want = min(designed, max(0, 4 - len(already)))
            if len(already) + want < 2:
                want = 2 - len(already)

        uniq, seen = [], set()
        for t in cand:
            if len(uniq) >= want:
                break
            if t == pid or t not in ok or t in already or t in seen:
                continue
            seen.add(t)
            uniq.append(t)

        if not uniq:
            # 一覧を出さない。前に入れた一覧が残っていれば外す
            if BLOCK_RE.search(raw) and not DRY_RUN:
                stripped = BLOCK_RE.sub("", raw).replace("\n\n\n", "\n\n")
                requests.post(f"{WP}/posts/{pid}", auth=AUTH, headers=UA,
                              verify=False, timeout=60,
                              json={"content": stripped})
            L.append(f"| {pid} | {LABEL.get(KIND.get(pid, ''), '—')} | "
                     f"一覧なし | 地の文にすでに{len(already)}本ある |\n")
            print(f"[{pid}] 一覧なし（地の文に{len(already)}本）")
            continue

        head = ("この記事のテーマで、次に読むと決めやすいもの"
                if role == "hub" else "あわせて確認したいもの")
        items = ""
        for t in uniq:
            note = cannibal_note(pid, t)
            suffix = f"（{note}）" if note else ""
            items += (f'<li><a href="{ok[t]["link"]}">{ROLE[t][2]}</a>'
                      f'{suffix}</li>\n')
        block = (f"{MARK_START}\n<h2>{head}</h2>\n<ul>\n{items}</ul>\n"
                 f"{MARK_END}")

        # すでに入っていれば置き換える。無ければ末尾のPR表記の前に入れる
        if BLOCK_RE.search(raw):
            new = BLOCK_RE.sub(block, raw)
        else:
            m = re.search(r"<p>※本記事にはアフィリエイトリンク", raw)
            new = (raw[:m.start()] + block + "\n" + raw[m.start():]
                   if m else raw + "\n" + block)

        names = " / ".join(ROLE[t][2][:20] for t in uniq)
        if DRY_RUN:
            L.append(f"| {pid} | {role} | {len(uniq)}本: {names} | （DRY RUN） |\n")
            print(f"[{pid}] {role} → {uniq}（DRY RUN）")
            continue
        up = requests.post(f"{WP}/posts/{pid}", auth=AUTH, headers=UA,
                           verify=False, timeout=60, json={"content": new})
        okk = up.status_code in (200, 201)
        applied += 1 if okk else 0
        L.append(f"| {pid} | {role} | {len(uniq)}本: {names} | "
                 f"{'✅ 反映' if okk else '❌ ' + str(up.status_code)} |\n")
        print(f"[{pid}] {role} → {uniq} {'OK' if okk else up.status_code}")

    L.append(f"\n**{applied}本に反映した。**\n\n"
             f"バックアップ: `workspace/backups/{day}/links/<記事ID>.json`\n"
             "戻すときは `content_raw` をそのまま書き戻す。\n")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "INTERNAL_LINKS.md").write_text("".join(L), encoding="utf-8")
    print(f"\n{applied}本 → workspace/seo/INTERNAL_LINKS.md")


if __name__ == "__main__":
    main()
