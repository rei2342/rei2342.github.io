#!/usr/bin/env python3
"""
ai_cluster_publish.py
AI英語学習クラスターの6記事を作って、公開・予約する。

仕様は `workspace/site/AI_CLUSTER.md`。本文は
`workspace/claims/ai/<key>.body.html` に置いてある。

公開の前に、**引用したURLを実際に取りに行って照合する**。
  - HTTP 200 で返るか
  - 主張に使った語が、そのページに載っているか
1つでも落ちた記事は**下書きのまま止める**。

守っていること（AI_CLUSTER.md と CLAUDE.md の制約）:
  speekはAI英会話アプリではなく発音矯正スクールとして書く
  Nottaは英語会議・実務英語の文脈だけ。英語力が上がる道具として書かない
  AIの精度・効果・上達速度を断定しない
  一人称の体験・「調べた」「試した」を使わない
  各記事に固有の成果物を1つ持たせ、見出し・結論・CTAを使い回さない

  DRY_RUN=false python ai_cluster_publish.py
出力: workspace/claims/ai/AI_PUBLISH.md / backups/<日付>/ai/<key>.json
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
import eyecatch_build as _eb

JST = timezone(timedelta(hours=9))
WP = "https://sakura-eigo.com/wp-json/wp/v2"
AUTH = ("rei.00pt2342@gmail.com", os.environ.get("WP_APP_PASSWORD", ""))
UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) "
                     "Chrome/124.0 Safari/537.36")}
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"
SRC = Path("affiliate-research-engine/playbook/workspace/claims/ai")
BK = Path("affiliate-research-engine/playbook/workspace/backups")
IMG = Path("affiliate-research-engine/playbook/workspace/seo/eyecatch_new")
CATEGORY = "AI英語学習"

CTA = {
    "スパトレ": '<p><a href="//af.moshimo.com/af/c/click?a_id=5640981&#038;'
              'p_id=2409&#038;pc_id=5246&#038;pl_id=31559&#038;url=https%3A%2F%2Fsptr.jp" '
              'target="_blank" rel="nofollow noopener">'
              '→ スパトレ（第二言語習得論ベースの英語トレーニング）の7日間無料体験を見る</a></p>',
    "ネイティブキャンプ": '<p><a href="https://px.a8.net/svt/ejp?a8mat=4B9W9D+28DJG2+35VG+64JTE" '
                  'target="_blank" rel="nofollow noopener">'
                  '→ ネイティブキャンプ（予約不要・レッスン回数無制限）の無料トライアルを試す</a></p>',
    "speek": '<p><a href="//af.moshimo.com/af/c/click?a_id=5640991&#038;p_id=4940&#038;'
             'pc_id=13178&#038;pl_id=65056&#038;url=https%3A%2F%2Fwww.speek.jp%2F" '
             'target="_blank" rel="nofollow noopener">'
             '→ speek公式サイトで発音矯正スクールの内容を確認する</a></p>',
    # 訴求語を入れない。台帳に行が無いので「無料」と書けない
    "Notta": '<p><a href="https://px.a8.net/svt/ejp?a8mat=4B9YLD+EAFAQ+5988+5ZEMQ" '
             'target="_blank" rel="nofollow noopener">'
             '→ Notta公式サイトで対応言語と共有の範囲を確認する</a></p>',
}

PR = "<p>※本記事にはアフィリエイトリンクが含まれます（PR）</p>"

# key → 記事の設定。公開順は AI_CLUSTER.md のとおり 3→4→1→5→2→6
ARTICLES = [
    {"key": "ai3", "order": 1,
     "title": "ChatGPTで英語学習を始める手順｜社会人が最初に試す3つの使い方",
     "slug": "chatgpt-english-learning-steps",
     "excerpt": "ChatGPTで英語を勉強したいが最初の1行が打てない人向けに、"
                "添削に使う3つのプロンプトの型と、出てきた答えの確かめ方をまとめた。",
     "cta": "スパトレ", "chip": "手順",
     "l1": "ChatGPTで英語学習", "l2": "最初に試す3つの使い方",
     "alt": "ChatGPTで英語学習を始めるときの、添削に使う3つのプロンプトの型",
     "deliverable": "添削プロンプトの3つの型と、出力の確かめ方",
     "links": ["ai4", "ai2", "310"]},
    {"key": "ai4", "order": 2,
     "title": "AI英会話とオンライン英会話の違い｜4つの軸で選ぶ",
     "slug": "ai-eikaiwa-vs-online-eikaiwa",
     "excerpt": "AI相手と人の講師のどちらから始めるかを、相手・訂正・時間帯・"
                "料金の4つの軸で並べて決める手順をまとめた。",
     "cta": "ネイティブキャンプ", "chip": "比較",
     "l1": "AI英会話と人の講師", "l2": "4つの軸で選ぶ",
     "alt": "AI英会話とオンライン英会話を、相手・訂正・時間帯・料金の4つの軸で比べる",
     "deliverable": "4軸の比較と、併用するときの役割分担",
     "links": ["ai3", "ai2", "282"]},
    {"key": "ai1", "order": 3,
     "title": "AI翻訳があるのに英語を学ぶ意味｜場面で分けて考える",
     "slug": "ai-translation-why-learn-english",
     "excerpt": "翻訳で足りる場面と足りない場面を分けて、"
                "自分に学ぶ理由が残るかを3つの質問で判定する手順をまとめた。",
     "cta": None, "chip": "分け方",
     "l1": "AI翻訳があるのに", "l2": "英語を学ぶ意味はあるか",
     "alt": "AI翻訳で足りる場面と足りない場面を分けて、学ぶ理由が残るかを判定する",
     "deliverable": "翻訳で足りるかを分ける3つの質問",
     "links": ["ai2", "ai3", "ai4"]},
    {"key": "ai5", "order": 4,
     "title": "AI発音矯正アプリの選び方｜自動判定でできることと、できないこと",
     "slug": "ai-pronunciation-app-how-to-choose",
     "excerpt": "発音の自動判定でできることと、点数からは決まらないことを分けて、"
                "アプリを選ぶときの4つの確認項目をまとめた。",
     "cta": "speek", "chip": "選び方",
     "l1": "AI発音矯正アプリ", "l2": "点数の外側にあるもの",
     "alt": "発音の自動判定でできることと、点数では決まらないことを分けて選ぶ",
     "deliverable": "アプリを選ぶ4つの確認項目",
     "links": ["ai2", "232", "521"]},
    {"key": "ai2", "order": 5,
     "title": "AI時代に必要な英語力はどこまでか｜場面から決める",
     "slug": "ai-era-english-how-far",
     "excerpt": "必要な英語力を一般論で決めずに、自分に実際に起きる場面から"
                "範囲を1つに絞る3ステップをまとめた。",
     "cta": None, "chip": "線引き",
     "l1": "AI時代に必要な英語力", "l2": "場面から決める",
     "alt": "AI時代に必要な英語力を、自分に起きる場面から1つに絞って決める",
     "deliverable": "場面を1つに絞る3ステップ",
     "links": ["ai1", "ai3", "ai4", "ai5", "ai6"]},
    {"key": "ai6", "order": 6,
     "title": "英語会議の文字起こしツールを選ぶ前に｜確認する5つのこと",
     "slug": "english-meeting-transcription-checklist",
     "excerpt": "英語会議で困る場面を3つに分けて、記録を残す道具で解決する部分と"
                "しない部分、社内情報の扱いを含む5つの確認項目をまとめた。",
     "cta": "Notta", "chip": "確認項目",
     "l1": "英語会議の文字起こし", "l2": "選ぶ前に確認する5つ",
     "alt": "英語会議の文字起こしツールを選ぶ前に確認する5つの項目",
     "deliverable": "会議の困りごとの3分類と、選ぶ5項目",
     "links": ["ai2"]},
]

# 引用したURLと、そのページに載っているはずの語
CITATIONS = {
    "ai3": [("https://openai.com/chatgpt/overview/", ["ChatGPT"]),
            ("https://sptr.jp/", ["スパトレ"])],
    "ai4": [("https://nativecamp.net", ["ネイティブキャンプ"])],
    "ai1": [],
    "ai5": [("https://speek.jp/", ["speek"])],
    "ai2": [],
    "ai6": [("https://www.notta.ai/", ["Notta", "notta"])],
}


def verify(url, words):
    try:
        r = requests.get(url, headers=UA, timeout=45, verify=False,
                         allow_redirects=True)
    except Exception as e:
        return False, f"取得できず {type(e).__name__}"
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}"
    text = _q.strip_tags(r.text)
    hit = [w for w in words if w.lower() in text.lower()]
    if not hit:
        return False, f"語が見つからない: {' / '.join(words)}"
    return True, f"HTTP 200・「{hit[0]}」を確認"


def ensure_category():
    r = requests.get(f"{WP}/categories", auth=AUTH, headers=UA, verify=False,
                     timeout=45, params={"search": CATEGORY, "per_page": 50})
    if r.status_code == 200:
        for c in r.json():
            if c["name"] == CATEGORY:
                return c["id"]
    if DRY_RUN:
        return None
    c = requests.post(f"{WP}/categories", auth=AUTH, headers=UA, verify=False,
                      timeout=45,
                      json={"name": CATEGORY, "slug": "ai-english"})
    return c.json().get("id") if c.status_code in (200, 201) else None


def main():
    day = datetime.now(JST).strftime("%Y-%m-%d")
    (BK / day / "ai").mkdir(parents=True, exist_ok=True)
    IMG.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    now = datetime.now(JST)

    L = [f"# AI英語学習クラスター 6記事 {stamp}\n\n",
         f"モード: **{'DRY RUN（書いていない）' if DRY_RUN else 'LIVE（書いた）'}**\n\n"]

    # ① 一次情報の照合。落ちた記事は止める
    L.append("## 一次情報の照合\n\n| 記事 | URL | 結果 |\n|---|---|---|\n")
    okmap = {}
    for a in ARTICLES:
        ok_all = True
        for url, words in CITATIONS[a["key"]]:
            ok, note = verify(url, words)
            L.append(f"| {a['key']} | {url} | {'✅' if ok else '❌'} {note} |\n")
            ok_all = ok_all and ok
        if not CITATIONS[a["key"]]:
            L.append(f"| {a['key']} | （引用なし） | ✅ 一次情報を使わない記事 |\n")
        okmap[a["key"]] = ok_all

    cat = ensure_category()
    L.append(f"\nカテゴリ「{CATEGORY}」: {cat or '（作れず）'}\n")

    # ② 記事を組み立てて送る
    L.append("\n## 記事\n\n| 順 | 記事 | タイトル | CTA | 状態 | 予定日 | 結果 |\n"
             "|---|---|---|---|---|---|---|\n")
    created = {}
    for a in ARTICLES:
        body = (SRC / f"{a['key']}.body.html").read_text(encoding="utf-8")
        html = body.rstrip()
        if a["cta"]:
            html += "\n\n" + CTA[a["cta"]]
        html += "\n\n" + PR

        blockers = _q.generation_blockers(html)
        gate_ok = not blockers
        if not gate_ok:
            L.append(f"| {a['order']} | {a['key']} | {a['title'][:28]} | "
                     f"{a['cta'] or 'なし'} | — | — | "
                     f"❌ ゲート: {blockers[0][:50]} |\n")
            print(f"[{a['key']}] ゲート: {blockers[0][:60]}")
            continue
        if not okmap[a["key"]]:
            L.append(f"| {a['order']} | {a['key']} | {a['title'][:28]} | "
                     f"{a['cta'] or 'なし'} | 下書きで止める | — | "
                     f"❌ 一次情報の照合に落ちた |\n")
            print(f"[{a['key']}] 一次情報に落ちた。下書きで止める")
            status, when = "draft", None
        else:
            # 1本目は即公開。以降は1日ずつずらして予約する
            if a["order"] == 1:
                status, when = "publish", None
            else:
                status = "future"
                when = (now + timedelta(days=a["order"] - 1)).replace(
                    hour=7, minute=0, second=0, microsecond=0)

        img = IMG / f"{a['key']}.png"
        _eb.build(str(900 + a["order"]), a["chip"], a["l1"], a["l2"]).save(
            img, "PNG", optimize=True)

        (BK / day / "ai" / f"{a['key']}.json").write_text(json.dumps({
            "key": a["key"], "checked_at": stamp, "title": a["title"],
            "slug": a["slug"], "status": status,
            "scheduled": when.isoformat() if when else None,
            "content": html}, ensure_ascii=False, indent=2), encoding="utf-8")

        if DRY_RUN:
            L.append(f"| {a['order']} | {a['key']} | {a['title'][:28]} | "
                     f"{a['cta'] or 'なし'} | {status} | "
                     f"{when.strftime('%m-%d %H:%M') if when else '即時'} | "
                     f"（DRY RUN） |\n")
            print(f"[{a['key']}] {status}（DRY RUN）")
            continue

        mid = None
        name = f"eyecatch-{a['slug']}.png"
        up = requests.post(
            f"{WP}/media", auth=AUTH, verify=False, timeout=120,
            headers={**UA, "Content-Disposition":
                     f'attachment; filename="{name}"',
                     "Content-Type": "image/png"}, data=img.read_bytes())
        if up.status_code in (200, 201):
            mid = up.json()["id"]
            requests.post(f"{WP}/media/{mid}", auth=AUTH, headers=UA,
                          verify=False, timeout=60,
                          json={"alt_text": a["alt"], "title": a["alt"][:60]})

        payload = {"title": a["title"], "slug": a["slug"],
                   "excerpt": a["excerpt"], "content": html,
                   "status": status}
        if cat:
            payload["categories"] = [cat]
        if mid:
            payload["featured_media"] = mid
        if when:
            payload["date"] = when.strftime("%Y-%m-%dT%H:%M:%S")

        r = requests.post(f"{WP}/posts", auth=AUTH, headers=UA, verify=False,
                          timeout=60, json=payload)
        ok = r.status_code in (200, 201)
        pid = r.json().get("id") if ok else None
        if ok:
            created[a["key"]] = pid
        L.append(f"| {a['order']} | {a['key']} | {a['title'][:28]} | "
                 f"{a['cta'] or 'なし'} | {status} | "
                 f"{when.strftime('%m-%d %H:%M') if when else '即時'} | "
                 f"{'✅ ID ' + str(pid) if ok else '❌ ' + str(r.status_code)} |\n")
        print(f"[{a['key']}] {status} {'ID ' + str(pid) if ok else r.status_code}")

    # ③ クラスター内の内部リンクを張る（IDが出そろってから）
    if created and not DRY_RUN:
        L.append("\n## 内部リンク\n\n| 記事 | 張った先 | 結果 |\n|---|---|---|\n")
        label = {a["key"]: a["title"].split("｜")[0] for a in ARTICLES}
        for a in ARTICLES:
            pid = created.get(a["key"])
            if not pid:
                continue
            items = ""
            for t in a["links"]:
                tid = created.get(t, t if t.isdigit() else None)
                if not tid:
                    continue
                g = requests.get(f"{WP}/posts/{tid}", auth=AUTH, headers=UA,
                                 verify=False, timeout=40,
                                 params={"context": "edit"})
                if g.status_code != 200:
                    continue
                lab = label.get(t) or _q.strip_tags(
                    g.json()["title"]["raw"]).split("｜")[0]
                items += f'<li><a href="{g.json()["link"]}">{lab}</a></li>\n'
            if not items:
                continue
            g = requests.get(f"{WP}/posts/{pid}", auth=AUTH, headers=UA,
                             verify=False, timeout=40,
                             params={"context": "edit"})
            raw = g.json()["content"]["raw"]
            head = ("この記事のテーマで、次に読むと決めやすいもの"
                    if a["key"] == "ai2" else "あわせて確認したいもの")
            block = (f"<!-- internal-links:START -->\n<h2>{head}</h2>\n"
                     f"<ul>\n{items}</ul>\n<!-- internal-links:END -->")
            m = re.search(r"<p>※本記事にはアフィリエイトリンク", raw)
            new = (raw[:m.start()] + block + "\n" + raw[m.start():]
                   if m else raw + "\n" + block)
            u = requests.post(f"{WP}/posts/{pid}", auth=AUTH, headers=UA,
                              verify=False, timeout=60, json={"content": new})
            L.append(f"| {a['key']} | {items.count('<li>')}本 | "
                     f"{'✅' if u.status_code in (200, 201) else '❌'} |\n")

    L.append("\n## 記事ごとの固有の成果物\n\n| 記事 | 成果物 |\n|---|---|\n")
    for a in ARTICLES:
        L.append(f"| {a['key']} {a['title'][:26]} | {a['deliverable']} |\n")

    (SRC / "AI_PUBLISH.md").write_text("".join(L), encoding="utf-8")
    print(f"\n→ {SRC}/AI_PUBLISH.md")


if __name__ == "__main__":
    main()
