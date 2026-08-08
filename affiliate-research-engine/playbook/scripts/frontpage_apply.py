#!/usr/bin/env python3
"""
frontpage_apply.py
トップページを固定ページにする。**記事一覧への入口を先に作ってから切り替える。**

順番が大事:
  1. いまのホーム表示設定をバックアップ
  2. 「記事一覧」の固定ページを作る（投稿ページになる）
  3. トップ用の固定ページを作る
  4. ホーム＝トップ / 投稿ページ＝記事一覧 に切り替える

**先に記事一覧を作らずに固定化すると、最新記事への入口が消える。**

  DRY_RUN=false python frontpage_apply.py
出力: workspace/backups/<日付>/frontpage.json / FRONTPAGE.md
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

JST = timezone(timedelta(hours=9))
SITE = "https://sakura-eigo.com"
WP = f"{SITE}/wp-json/wp/v2"
WP_USER = "rei.00pt2342@gmail.com"
WP_PASS = os.environ.get("WP_APP_PASSWORD", "")
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"
BK = Path("affiliate-research-engine/playbook/workspace/backups")
UA = {"User-Agent": "Mozilla/5.0"}
AUTH = (WP_USER, WP_PASS)

# 既存カテゴリのslug。**1つも変更しない**（変えると301が要る）
CAT = {
    "学習法": "%e8%8b%b1%e8%aa%9e%e5%ad%a6%e7%bf%92%e6%b3%95",
    "比較": "%e8%8b%b1%e4%bc%9a%e8%a9%b1%e3%82%b5%e3%83%bc%e3%83%93%e3%82%b9%e6%af%94%e8%bc%83",
    "コーチング": "%e8%8b%b1%e8%aa%9e%e3%82%b3%e3%83%bc%e3%83%81%e3%83%b3%e3%82%b0",
    "留学": "%e6%b5%b7%e5%a4%96%e7%95%99%e5%ad%a6%e3%83%bb%e3%83%af%e3%83%bc%e3%83%9b%e3%83%aa",
}

# TOEIC・スコアへ移す記事。**主カテゴリを1つにする**
TOEIC_POSTS = ["304", "521", "32"]

ARTICLES_SLUG = "articles"
FRONT_SLUG = "start"

ARTICLES_BODY = """<p>新しい記事から順に並んでいます。テーマから探す場合は、
<a href="https://sakura-eigo.com/">トップページ</a>の「テーマから読む」を使ってください。</p>
"""


def get_pages():
    r = requests.get(f"{WP}/pages", auth=AUTH, headers=UA, verify=False,
                     timeout=40, params={"per_page": 100, "status": "publish,draft"})
    return r.json() if r.status_code == 200 else []


def get_cats():
    r = requests.get(f"{WP}/categories", auth=AUTH, headers=UA, verify=False,
                     timeout=40, params={"per_page": 100})
    return {c["slug"]: c for c in (r.json() if r.status_code == 200 else [])}


def front_body(cats):
    """トップページの本文。空カテゴリは目立たせない。"""
    def cat_line(slug, label, desc):
        c = cats.get(slug)
        if not c:
            return ""
        n = c.get("count", 0)
        if n == 0:
            # 記事が0本のカテゴリはリンクにしない。準備中と書くだけ
            return f"<li>{label}（準備中）<br><span>{desc}</span></li>\n"
        return (f'<li><a href="{SITE}/category/{slug}/"><strong>{label}</strong></a>'
                f'（{n}本）<br><span>{desc}</span></li>\n')

    # slug は既存のものをそのまま使う。URLエンコードされた日本語slugも変えない
    cat_html = "".join([
        cat_line(CAT["学習法"], "英語学習法", "続かない理由を、意志ではなく形から見直す"),
        cat_line("toeic-score", "TOEIC・スコア", "止まったスコアの内訳を分解して、次に直す場所を決める"),
        cat_line(CAT["比較"], "英会話サービス比較", "アプリ・オンライン英会話の比べ方"),
        cat_line(CAT["コーチング"], "英語コーチング", "払う前に確認することと、卒業後に残るもの"),
        cat_line("ai-english", "AI英語学習", "AI翻訳・ChatGPT・AI英会話をどう使うか"),
        cat_line(CAT["留学"], "海外留学・ワーホリ", "費用の出し方、エージェントの選び方、制度の確認"),
        cat_line("philippines-cebu", "フィリピン・セブ留学", "学校の選び方と、費用の内訳"),
        cat_line("ryugaku-agent-cost", "留学エージェント・費用", "手数料の仕組みと、聞く質問"),
    ])

    return f"""<h2>働きながら英語をやり直したい人へ</h2>

<p>英語をやり直そうと思ったとき、いちばん困るのは「何から手を付けるか」が決まらないことだと思います。</p>

<p>このサイトでは、次の3つを整理しています。</p>

<ul>
<li>自分に合う勉強法の選び方</li>
<li>サービスの比べ方（料金の安さだけで選ばない方法）</li>
<li>留学やワーホリにかかる費用の出し方</li>
</ul>

<h2>いまの悩みから読む</h2>

<ul>
<li><a href="{SITE}/cheap-english-learning-apps-free/">勉強が続かない／安いアプリで足りるか知りたい</a></li>
<li><a href="{SITE}/toeic-600-plateau-breakthrough-study/">TOEICが600点前後で止まっている</a></li>
<li><a href="{SITE}/toeic-listening-325-to-improvement/">リスニングだけ動かない</a></li>
<li><a href="{SITE}/philippines-study-abroad-adult-costs/">留学・ワーホリの費用を知りたい</a></li>
<li><a href="{SITE}/english-coaching-after-graduation/">英語コーチングを検討している</a></li>
</ul>

<h2>テーマから読む</h2>

<ul>
{cat_html}</ul>

<p><a href="{SITE}/{ARTICLES_SLUG}/"><strong>新しい記事を順番に見る（記事一覧）</strong></a></p>

<h2>このサイトの書き方</h2>

<ul>
<li>実際に試したものは、確認できる範囲を体験として掲載します。</li>
<li>まだ使っていないサービスは、公式情報をもとに機能や選び方を整理します。使ったふりはしません。</li>
<li>料金・制度・キャンペーンなど変わる情報には、出典のURLと確認日を付けています。</li>
<li>効果や必要な時間を保証しません。「これをやれば伸びる」ではなく、「自分の場合はどうかを確かめる方法」を書いています。</li>
<li>公式情報と、編集上の提案は分けて表示しています。記事の中で「公式情報」「確認項目」「提案」とラベルを付けているのはそのためです。</li>
</ul>

<h2>書いている人</h2>

<p><strong>さくら｜大人の英語学び直し案内人</strong></p>

<p>英語を話せるようになりたいけれど、何から始めればいいか決まらない人に向けて、勉強法・サービス・留学の選び方を整理しています。</p>

<p>先に正解へたどり着いた人ではありません。英語学習でつまずきやすいところを調べて、判断しやすい形に並べ直すのが役割です。</p>

<p>実際に試したものは、確認できる範囲を体験として書きます。まだ使っていないサービスは、公式情報をもとに整理します。料金や制度は公式サイトで確認して、確認日を付けています。</p>

<h2>広告について</h2>

<p>当サイトにはアフィリエイトリンクが含まれます。リンクから申し込みがあった場合、当サイトに報酬が入ることがあります。紹介するサービスは、公式サイトで内容を確認したものだけにしています。報酬の有無で順番や評価を変えていません。</p>
"""


def ensure_page(pages, slug, title, content):
    """slug のページを作るか、あれば更新する。"""
    hit = next((p for p in pages if p["slug"] == slug), None)
    if hit:
        if DRY_RUN:
            return hit["id"], "すでにある（更新する）"
        r = requests.post(f"{WP}/pages/{hit['id']}", auth=AUTH, headers=UA,
                          verify=False, timeout=60,
                          json={"title": title, "content": content,
                                "status": "publish"})
        return hit["id"], ("✅ 更新" if r.status_code in (200, 201)
                           else f"❌ {r.status_code}")
    if DRY_RUN:
        return None, "新規作成する（DRY RUN）"
    r = requests.post(f"{WP}/pages", auth=AUTH, headers=UA, verify=False,
                      timeout=60, json={"title": title, "slug": slug,
                                        "content": content, "status": "publish"})
    if r.status_code in (200, 201):
        return r.json()["id"], "✅ 作成"
    return None, f"❌ {r.status_code} {r.text[:150]}"


def main():
    day = datetime.now(JST).strftime("%Y-%m-%d")
    (BK / day).mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    L = [f"# トップページの固定化 {stamp}\n\n",
         f"モード: **{'DRY RUN（書いていない）' if DRY_RUN else 'LIVE（書いた）'}**\n\n"]

    s = requests.get(f"{WP}/settings", auth=AUTH, headers=UA, verify=False,
                     timeout=40)
    settings = s.json() if s.status_code == 200 else {}
    pages = get_pages()
    cats = get_cats()

    (BK / day / "frontpage.json").write_text(json.dumps({
        "checked_at": stamp, "settings": settings,
        "pages": [{"id": p["id"], "slug": p["slug"],
                   "title": p["title"]["rendered"]} for p in pages],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    L.append("## 反映前のホーム表示設定（バックアップ済み）\n\n")
    for k in ("show_on_front", "page_on_front", "page_for_posts", "posts_per_page"):
        L.append(f"- `{k}`: **{settings.get(k)}**\n")
    L.append(f"- 固定ページ: {len(pages)}件\n")
    L.append(f"- バックアップ: `workspace/backups/{day}/frontpage.json`\n\n")
    print("show_on_front:", settings.get("show_on_front"))
    print("pages:", [(p["slug"], p["id"]) for p in pages])
    print("cats:", [(k, v.get("count")) for k, v in cats.items()])

    # ── 1. 記事一覧ページを先に作る ──────────────────
    L.append("## 1. 記事一覧ページ（先に作る）\n\n")
    aid, amsg = ensure_page(pages, ARTICLES_SLUG, "記事一覧", ARTICLES_BODY)
    L.append(f"- slug `{ARTICLES_SLUG}` … {amsg}（ID {aid}）\n")
    L.append(f"- URL: {SITE}/{ARTICLES_SLUG}/\n\n")
    print(f"記事一覧: {amsg} id={aid}")

    # ── 2. トップページ ────────────────────────────
    L.append("## 2. トップページ\n\n")
    fid, fmsg = ensure_page(pages, FRONT_SLUG, "さくらの大人英語学び直しガイド",
                            front_body(cats))
    L.append(f"- slug `{FRONT_SLUG}` … {fmsg}（ID {fid}）\n\n")
    print(f"トップ: {fmsg} id={fid}")

    # 空カテゴリの扱いを記録
    L.append("### カテゴリ導線（記事が0本のものはリンクにしない）\n\n")
    L.append("| カテゴリ | slug | 記事数 | 扱い |\n|---|---|---|---|\n")
    for slug, label in ((CAT["学習法"], "英語学習法"),
                        ("toeic-score", "TOEIC・スコア"),
                        (CAT["比較"], "英会話サービス比較"),
                        (CAT["コーチング"], "英語コーチング"),
                        ("ai-english", "AI英語学習"),
                        (CAT["留学"], "海外留学・ワーホリ"),
                        ("philippines-cebu", "フィリピン・セブ留学"),
                        ("ryugaku-agent-cost", "留学エージェント・費用")):
        c = cats.get(slug)
        n = c.get("count", 0) if c else "（カテゴリ無し）"
        how = ("リンクにする" if isinstance(n, int) and n > 0
               else "**準備中と書くだけ。リンクにしない**")
        L.append(f"| {label} | `{slug}` | {n} | {how} |\n")

    # ── 3. ホーム表示の切り替え ────────────────────
    L.append("\n## 3. ホーム表示の切り替え\n\n")
    if not (aid and fid):
        L.append("⚠️ ページIDが揃わないので**切り替えない**。\n")
        print("ページIDが揃わないので切り替えない")
    elif DRY_RUN:
        L.append(f"- `show_on_front` → `page`\n- `page_on_front` → {fid}\n"
                 f"- `page_for_posts` → {aid}\n\n→ （DRY RUN）\n")
    else:
        up = requests.post(f"{WP}/settings", auth=AUTH, headers=UA, verify=False,
                           timeout=40, json={"show_on_front": "page",
                                             "page_on_front": fid,
                                             "page_for_posts": aid})
        ok = up.status_code in (200, 201)
        L.append(f"- `show_on_front` → `page`\n- `page_on_front` → {fid}\n"
                 f"- `page_for_posts` → {aid}\n\n"
                 f"→ {'✅ 反映した' if ok else '❌ ' + str(up.status_code) + ' ' + up.text[:200]}\n")
        print(f"切り替え: {'OK' if ok else up.status_code}")

    # ── 4. TOEIC記事を新カテゴリへ移す（主カテゴリ1つ）──
    tc = cats.get("toeic-score")
    L.append("\n## 4. TOEIC記事のカテゴリ割り当て\n\n")
    if not tc:
        L.append("⚠️ `toeic-score` が無いので割り当てない\n")
    else:
        L.append("**主カテゴリを1つにする。**過剰に付けない。\n\n")
        L.append("| 記事 | 前 | 後 |\n|---|---|---|\n")
        for pid in TOEIC_POSTS:
            g = requests.get(f"{WP}/posts/{pid}", auth=AUTH, headers=UA,
                             verify=False, timeout=40)
            if g.status_code != 200:
                L.append(f"| {pid} | 取得できず | — |\n")
                continue
            before = g.json().get("categories", [])
            if DRY_RUN:
                L.append(f"| {pid} | {before} | [{tc['id']}]（DRY RUN） |\n")
                continue
            up = requests.post(f"{WP}/posts/{pid}", auth=AUTH, headers=UA,
                               verify=False, timeout=40,
                               json={"categories": [tc["id"]]})
            ok = up.status_code in (200, 201)
            L.append(f"| {pid} | {before} | "
                     f"{'✅ [' + str(tc['id']) + ']' if ok else '❌ ' + str(up.status_code)} |\n")
            print(f"[{pid}] categories {before} -> [{tc['id']}] {'OK' if ok else up.status_code}")

    # ── 5. Uncategorized に残る公開記事 ──────────────
    uc = cats.get("uncategorized")
    L.append("\n## 5. Uncategorized に残る公開記事\n\n")
    if uc:
        L.append(f"- 記事数: **{uc.get('count', 0)}本**"
                 + ("（移す対象なし）" if uc.get("count", 0) == 0 else "") + "\n")

    (BK / day / "FRONTPAGE.md").write_text("".join(L), encoding="utf-8")
    print(f"\n→ workspace/backups/{day}/FRONTPAGE.md")


if __name__ == "__main__":
    main()
