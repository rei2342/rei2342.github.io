#!/usr/bin/env python3
"""
official_fact_check.py
記事に書く「公式情報」を、公式ページだけで裏取りする。

**第三者のまとめ記事・検索結果の要約は使わない。** 許可したドメインしか見ない。
取れた根拠をそのまま保存して、あとから誰でも同じ確認ができる形にする。

  CHECKS=toeic python official_fact_check.py
出力: workspace/claims/OFFICIAL_FACTS.md / .csv
"""
import csv
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

OUT = Path("affiliate-research-engine/playbook/workspace/claims")
JST = timezone(timedelta(hours=9))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# ここに書いたドメインしか見ない。IIBC（日本の運営団体）と ETS（開発元）
ALLOWED = ("iibc-global.org", "ets.org", "qqeng.com", "callan.co.uk",
           "sptr.jp", "speek.jp", "nativecamp.net",
           # 2026-08-09に追加。CTAで「無料」を訴求しているのに
           # cta_claims.csv に行が無い案件を裏取りするため
           "eikaiwa.dmm.com", "rarejob.com", "eigosapuri.jp",
           "u-gaku.jp", "ryugaku-johokan.com", "cebridge.jp", "notta.ai",
           # ワーホリの年齢条件の一次情報。**外務省と各国の公的機関だけ。**
           # まとめサイト・エージェントの説明は根拠にしない
           "mofa.go.jp", "immi.gov.au", "homeaffairs.gov.au",
           "canada.ca", "cic.gc.ca", "immigration.govt.nz")

# (主張ID, 記事, 主張, 見に行くURL, 根拠として探す語)
CHECKS = [
    ("T1", "304",
     "TOEIC L&R の結果はリスニングとリーディングのスコアが別々に返ってくる",
     ["https://www.iibc-global.org/toeic/test/lr/about/score.html",
      "https://www.iibc-global.org/toeic/test/lr/about/audience.html",
      "https://www.iibc-global.org/toeic/test/lr.html"],
     ["リスニング", "リーディング", "スコア", "5点", "495"]),
    ("T2", "282",
     "TOEIC L&R は聞いて選ぶ・読んで選ぶ形式で、発話の設問は含まれない",
     ["https://www.iibc-global.org/toeic/test/lr/about/format.html",
      "https://www.iibc-global.org/toeic/test/lr/about/outline.html",
      "https://www.iibc-global.org/toeic/test/lr.html"],
     ["マークシート", "選択", "リスニング", "リーディング", "200問"]),
    ("T3", "282",
     "話す力を測るテストは別にある（TOEIC Speaking）",
     ["https://www.iibc-global.org/toeic/test/sw.html",
      "https://www.iibc-global.org/toeic.html"],
     ["Speaking", "スピーキング", "話す"]),
    ("Q1", "callan",
     "QQ Englishの無料体験レッスンは2回まで",
     ["https://www.qqeng.com/", "https://www.qqeng.com/price/"],
     ["無料体験", "2回", "体験レッスン"]),
    ("Q2", "callan",
     "QQ Englishはカランメソッドの正式認定校",
     ["https://www.qqeng.com/", "https://www.qqeng.com/callan/"],
     ["正式認定校", "カランメソッド", "認定"]),
    ("Q3", "callan",
     "カランメソッドは通常の4倍速で、ケンブリッジ検定に350時間が80時間になったという実績",
     ["https://www.callan.co.uk/", "https://www.qqeng.com/callan/"],
     ["4倍", "four times", "350", "80"]),
    # ── CTAの「無料」訴求の裏取り（2026-08-09に追加）──────────────
    # 生成側の全CTAをゲートに掛けたら、15本中8本が cta_claims.csv に
    # 行が無いまま「無料」と書いていた。**アンカー文言は先に中立化した**うえで、
    # 公式に書いてある範囲を確認して台帳に載せ直す。
    #
    # ⚠️ 見に行くURLの出どころを2種類に分ける。
    #   [リンク由来] もしもリンクの url= パラメータから取れた。踏まずに確認できる
    #   [推定]      A8リンクは遷移先がURLに入っていないので、こちらでドメインを推定した。
    #               **ページタイトルが案件名と一致することを人が見て確かめる。**
    ("A1", "cta", "[リンク由来] U-GAKUの無料オンライン個別相談",
     ["https://u-gaku.jp/"], ["無料", "個別相談", "カウンセリング", "相談"]),
    ("A2", "cta", "[リンク由来] CEBRIDGEの無料カウンセリング",
     ["https://cebridge.jp/"], ["無料", "カウンセリング", "相談"]),
    ("A3", "cta", "[推定] DMM英会話の無料体験レッスン",
     ["https://eikaiwa.dmm.com/"], ["無料体験", "無料", "体験レッスン", "回"]),
    ("A4", "cta", "[推定] レアジョブ英会話の無料体験レッスン",
     ["https://www.rarejob.com/"], ["無料体験", "無料", "体験レッスン", "回"]),
    ("A5", "cta", "[推定] スタディサプリENGLISHの無料体験",
     ["https://eigosapuri.jp/"], ["無料体験", "無料", "日間", "体験"]),
    ("A6", "cta", "[推定] Nottaの無料プラン",
     ["https://www.notta.ai/"], ["無料", "無料プラン", "分"]),
    ("A7", "cta", "[リンク由来] 留学情報館の無料カウンセリング",
     ["https://www.ryugaku-johokan.com/index_mr.php"],
     ["無料", "手数料", "カウンセリング", "0円"]),
    # ── ワーホリの年齢条件（2026-08-09に追加）────────────────
    # 記事289・292・238が「申請時点で原則30歳まで」「31歳の誕生日の前日まで
    # 申請すれば渡航は32歳でも大丈夫」と書いている。
    # **国を特定せずに書いてある**ので、外務省の一次情報と照合する。
    # 近い制度から推測して補わない。取れなければ削除する。
    ("W1", "289,292", "ワーキング・ホリデー制度の対象年齢（外務省の一覧）",
     ["https://www.mofa.go.jp/mofaj/toko/visa/working_h.html",
      "https://www.mofa.go.jp/mofaj/toko/page22_000969.html"],
     ["18歳", "25歳", "30歳", "年齢", "対象", "ワーキング・ホリデー"]),
    ("W2", "238", "申請時と渡航時のどちらで年齢を判定するか",
     ["https://www.mofa.go.jp/mofaj/toko/visa/working_h.html"],
     ["申請時", "査証申請", "発給", "入国", "有効期間", "1年"]),
    ("T4", "32",
     "成績票に項目別の正答率（Abilities Measured）が記載されている",
     ["https://www.iibc-global.org/toeic/test/lr/about/score.html",
      "https://www.iibc-global.org/toeic/test/lr/guide04.html",
      "https://www.iibc-global.org/toeic/support/lr/data.html"],
     ["Abilities Measured", "アビリティーズメジャード", "項目別", "正答率",
      "公式認定証", "デジタル公式認定証"]),
]


def allowed(url):
    return any(d in url for d in ALLOWED)


def fetch(url):
    if not allowed(url):
        return {"error": "許可していないドメイン"}
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=45,
                         allow_redirects=True, verify=False)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    if r.status_code != 200:
        return {"error": f"HTTP {r.status_code}", "final_url": r.url}
    html = r.text
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.I)
    return {"final_url": r.url, "status": r.status_code,
            "title": re.sub(r"\s+", " ", _q.strip_tags(m.group(1))).strip() if m else "",
            "text": re.sub(r"\s+", " ", _q.strip_tags(html))}


def excerpt(text, word, span=90):
    i = text.find(word)
    if i < 0:
        return ""
    return text[max(0, i - span):i + span].strip()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    only = os.environ.get("CHECKS", "")
    rows, L = [], [
        f"# 公式情報の裏取り {stamp}\n\n",
        "**IIBC と ETS の公式ページだけを見ている。**\n"
        "第三者のまとめ記事・検索結果の要約は根拠にしていない。\n\n",
        "完全に一致した主張だけ official_fact として残す。\n"
        "部分一致なら、根拠が支持する範囲まで表現を弱める。\n\n"]

    for cid, pid, claim, urls, words in CHECKS:
        # CHECKS には check_id（T1 / Q2 / A3）か、まとめ名（toeic / cta / callan）
        # をカンマ区切りで書く。空なら全部見る
        if only:
            want = {w.strip().lower() for w in only.split(",") if w.strip()}
            group = {"toeic": cid.startswith("T"), "cta": cid.startswith("A"),
                     "callan": cid.startswith("Q"),
                     "workingholiday": cid.startswith("W")}
            if not (cid.lower() in want or pid.lower() in want
                    or any(group.get(w) for w in want)):
                continue
        L.append(f"\n---\n\n## {cid}（記事{pid}）\n\n**主張**: {claim}\n\n")
        print(f"\n[{cid}] {claim}")
        found = False
        for url in urls:
            r = fetch(url)
            if r.get("error"):
                L.append(f"- {url} … 取得できず（{r['error']}）\n")
                print(f"   × {url} {r['error']}")
                continue
            hits = [(w, excerpt(r["text"], w)) for w in words
                    if excerpt(r["text"], w)]
            L.append(f"\n### 公式ページ\n\n- **URL**: {r['final_url']}\n"
                     f"- **ページタイトル**: {r['title']}\n"
                     f"- **確認日**: {stamp}\n"
                     f"- **HTTP**: {r['status']}\n"
                     f"- **見つかった語**: "
                     f"{'・'.join(w for w, _ in hits) or '（なし）'}\n")
            print(f"   ○ {url} → {len(hits)}語一致")
            for w, ex in hits[:6]:
                L.append(f"\n**該当箇所（{w}）**\n\n> …{ex}…\n")
            rows.append({"check_id": cid, "post_id": pid, "claim": claim,
                         "url": r["final_url"], "title": r["title"],
                         "checked_at": stamp, "http": r["status"],
                         "matched_words": " ".join(w for w, _ in hits),
                         "excerpt": (hits[0][1][:300] if hits else "")})
            if hits:
                found = True
                break
        if not found:
            L.append("\n⚠️ **根拠が取れなかった。** この主張は削除するか、"
                     "読者向けの確認項目へ変更する。\n")
            print("   ⚠️ 根拠なし")

    if rows:
        with open(OUT / "OFFICIAL_FACTS.csv", "w", encoding="utf-8",
                  newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    (OUT / "OFFICIAL_FACTS.md").write_text("".join(L), encoding="utf-8")
    print(f"\n{len(rows)}件 → OFFICIAL_FACTS.md")


if __name__ == "__main__":
    main()
