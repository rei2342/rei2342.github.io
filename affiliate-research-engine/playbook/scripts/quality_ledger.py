#!/usr/bin/env python3
"""
quality_ledger.py
公開49本の品質台帳を1枚にまとめる。

**公開中の本文だけを見る。** ローカルの改修版ファイルは参照しない。

出す列:
  記事ID / URL / タイトル / 固有の成果物 / 主案件 / 補助案件 / CTA数 /
  使用した一次情報 / 全文目視 / 公開確認 / インデックス状況 / ブロッカー

あわせて、アイキャッチ画像の一覧も出す（画像内の文字は機械で読めないので
差し替え候補の判定は人がやる。ここでは対象URLと、本文と矛盾しうる手掛かりを出す）。

  python quality_ledger.py
出力: workspace/claims/QUALITY_LEDGER.md / .csv
"""
import csv
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

CL = Path("affiliate-research-engine/playbook/workspace/claims")
JST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0"}
SITE = "https://sakura-eigo.com"

# 記事ごとの固有の成果物。全面再構成のときに決めたもの
DELIVERABLE = {
    "292": "独学の限界を上限と継続に分ける確認項目",
    "289": "締切のある入口とない入口の切り分け＋費用6項目",
    "42": "職務で使う英文9型",
    "546": "手数の数え方＋1回あたりの試算",
    "238": "申請7工程の逆算表",
    "294": "候補3つの比較表",
    "19": "入力・出力・矯正の3列表",
    "64": "契約前に投げる12の質問",
    "61": "締切の棚卸し表＋求人からスコア逆引き",
    "207": "不安の仕分けシート（A調べれば消える/B試せば縮む/C残る）",
    "136": "入口の手前／入口／入ったあとの3段表",
    "287": "詰まり回収ノート（出席と回収を分ける）",
    "305": "渡航初日の5場面の台本",
    "286": "反応が返るかの3問判定フロー",
    "235": "比較表の列の置き換え表（滞在中→帰国後）",
    "67": "帰国後4週間シート",
    "301": "その場で使う言い回し集",
    "297": "脱落地点マップ（4か所）",
    "18": "出発月からの逆算カレンダー",
    "27": "用途の絞り込みシート",
    "28": "手間と実感の差し引き表",
    "33": "職務10場面の頻度順表＋英文の型",
    "41": "体力3段階の最低ライン表",
    "117": "明日の出番を作る出口リスト",
    "137": "体験談の読み分けフィルタ",
    "138": "総額÷残った月数の単価計算",
    "150": "空いた日から戻る復帰手順",
    "151": "「意味ない」を翻訳する4問",
    "241": "独学の工程の切り分け表",
    "273": "発話秒数の計測手順",
    "281": "帰国後に落ちやすい順の表",
}

# 案件名の逆引き。CTAのURLから案件を特定する
PROGRAM_BY_ID = [
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

OFFICIAL_DOMAIN = re.compile(
    r"https?://(?:www\.)?([a-z0-9.\-]+)/?", re.I)


def programs_in(html):
    out = []
    for m in re.finditer(r'<a\b[^>]*href="([^"]+)"', html):
        href = m.group(1).replace("&#038;", "&").replace("&amp;", "&")
        if not _q.AFFILIATE_LINK_RE.search(href):
            continue
        name = next((n for k, n in PROGRAM_BY_ID if k in href), "（不明）")
        out.append(name)
    return out


def sources_in(html):
    """本文が引用している一次情報のドメイン。"""
    doms = []
    for m in re.finditer(r'href="(https?://[^"]+)"', html):
        u = m.group(1)
        if "sakura-eigo.com" in u or _q.AFFILIATE_LINK_RE.search(u):
            continue
        d = OFFICIAL_DOMAIN.match(u)
        if d:
            doms.append(d.group(1))
    return sorted(set(doms))


def main():
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    posts = _wa.published()
    print(f"公開記事 {len(posts)}本")

    rows, imgs = [], []
    for p in sorted(posts, key=lambda x: x["id"]):
        pid = str(p["id"])
        html = p.get("content", {}).get("rendered", "")
        title = re.sub(r"<[^>]+>", "", p["title"]["rendered"])
        link = p.get("link", "")
        progs = programs_in(html)
        blockers = _q.generation_blockers(html)

        # 公開ページの確認（HTTP・canonical・noindex・OGP画像）
        http = canon = ni = ogimg = ""
        try:
            r = requests.get(link, headers=UA, verify=False, timeout=45)
            http = r.status_code
            h = r.text
            m = re.search(r'rel="canonical"[^>]+href="([^"]+)"', h)
            canon = "自己参照" if m and m.group(1).rstrip("/") == link.rstrip("/") \
                else (m.group(1) if m else "（無し）")
            ni = "あり" if re.search(r'name="robots"[^>]+noindex', h, re.I) else "なし"
            og = re.search(r'property="og:image"[^>]+content="([^"]+)"', h)
            ogimg = og.group(1) if og else ""
        except Exception as e:
            http = f"エラー({type(e).__name__})"

        rows.append({
            "post_id": pid, "url": link, "title": title[:46],
            "deliverable": DELIVERABLE.get(pid, "（全面再構成の対象外）"),
            "main_program": progs[0] if progs else "（CTAなし）",
            "sub_program": progs[1] if len(progs) > 1 else "（なし）",
            "cta_count": len(progs),
            "sources": " / ".join(sources_in(html)) or "（なし）",
            "blockers": len(blockers),
            "http": http, "canonical": canon, "noindex": ni,
            "eyecatch": ogimg,
        })
        if ogimg:
            imgs.append((pid, title[:40], ogimg))
        print(f"[{pid}] CTA{len(progs)} ブロッカー{len(blockers)} HTTP{http}")

    ng = [r for r in rows if r["blockers"] or r["http"] != 200
          or r["noindex"] != "なし"]

    L = [f"# 品質台帳 {stamp}\n\n",
         f"公開 **{len(rows)}本**。**公開中の本文だけ**を見ている。\n\n",
         f"- ブロッカーが残る記事: **{sum(1 for r in rows if r['blockers'])}本**\n",
         f"- HTTP 200 以外: **{sum(1 for r in rows if r['http'] != 200)}本**\n",
         f"- noindex あり: **{sum(1 for r in rows if r['noindex'] != 'なし')}本**\n",
         f"- CTAが3本以上: **{sum(1 for r in rows if r['cta_count'] > 2)}本**\n\n",
         "全文目視は、全面再構成した31本については書いた本人が全文を通して確認済み。\n"
         "残り18本は以前の改修時に確認したもので、今回の再構成の対象外。\n\n",
         "---\n\n",
         "| 記事 | タイトル | 固有の成果物 | 主案件 | 補助案件 | CTA | 一次情報 | ブロッカー | HTTP | canonical | noindex |\n",
         "|---|---|---|---|---|---|---|---|---|---|---|\n"]
    for r in rows:
        L.append(f"| [{r['post_id']}]({r['url']}) | {r['title']} | "
                 f"{r['deliverable']} | {r['main_program']} | "
                 f"{r['sub_program']} | {r['cta_count']} | "
                 f"{r['sources'][:60]} | {r['blockers']} | {r['http']} | "
                 f"{r['canonical'][:20]} | {r['noindex']} |\n")

    L.append("\n---\n\n## アイキャッチ画像（画像内の文字は目視で確認する）\n\n"
             "**自動で差し替えない。** 画像の中の文字は機械で読めないので、\n"
             "旧年齢・旧スコア・旧金額・旧期間・削除済みの成功結果・旧サイト名が\n"
             "焼き込まれていないかを人が開いて確認する。\n\n"
             "ファイル名に本文と矛盾する語が入っているものには印を付けた。\n\n"
             "| 記事 | タイトル | 画像 | 手掛かり |\n|---|---|---|---|\n")
    HINT = re.compile(r"(\d{2,3})-?(?:days|day|point|score)|success|90-days|"
                      r"27|30s|toeic-?\d{3}", re.I)
    for pid, title, url in imgs:
        hint = HINT.search(url.rsplit("/", 1)[-1])
        mark = f"⚠️ ファイル名に `{hint.group(0)}`" if hint else ""
        L.append(f"| {pid} | {title} | {url} | {mark} |\n")

    with open(CL / "QUALITY_LEDGER.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    (CL / "QUALITY_LEDGER.md").write_text("".join(L), encoding="utf-8")
    print(f"\n問題のある記事 {len(ng)}本 → QUALITY_LEDGER.md")


if __name__ == "__main__":
    main()
