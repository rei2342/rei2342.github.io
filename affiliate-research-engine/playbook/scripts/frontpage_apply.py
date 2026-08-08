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

PROFILE_BODY = """<h2>さくら｜大人の英語学び直し案内人</h2>

<p>英語を話せるようになりたいけれど、何から始めればいいか決まらない人に向けて、勉強法・サービス・留学の選び方を整理しています。</p>

<p>先に正解へたどり着いた人ではありません。英語学習でつまずきやすいところを調べて、判断しやすい形に並べ直すのが役割です。</p>

<h3>書き方の方針</h3>

<ul>
<li><strong>実際に試したものは、確認できる範囲を体験として書きます。</strong>記録で確かめられる範囲に限ります。</li>
<li><strong>まだ使っていないサービスは、公式情報をもとに整理します。</strong>使ったふりはしません。体験と公式情報は、記事の中で分けて表示しています。</li>
<li>料金・制度・キャンペーンなど変わる情報には、<strong>出典のURLと確認日</strong>を付けています。</li>
<li>効果や必要な時間を保証しません。「これをやれば伸びる」ではなく、「自分の場合はどうかを確かめる方法」を書いています。</li>
</ul>

<h3>扱っていること</h3>

<ul>
<li>続けやすい勉強法と教材の選び方</li>
<li>オンライン英会話・コーチング・アプリの比べ方</li>
<li>AI時代の英語学習の使いどころ</li>
<li>留学・ワーホリの費用の出し方と、エージェントの選び方</li>
</ul>

<p>当サイトにはアフィリエイトリンクが含まれます。紹介するサービスは、公式サイトで内容を確認したものだけにしています。報酬の有無で順番や評価を変えていません。</p>
"""

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

    # ── 1. TOEIC記事のカテゴリ割り当て（**ページ生成より先**）──
    # 先にページを作ると、移す前の件数（0本）でトップが生成されてしまう
    # （2026-08-09に「準備中」と出た。処理順のミス）
    tc = cats.get("toeic-score")
    L.append("## 1. TOEIC記事のカテゴリ割り当て（ページ生成より先に実行）\n\n")
    if not tc:
        L.append("⚠️ `toeic-score` が無いので割り当てない\n\n")
    else:
        L.append("**主カテゴリを1つにする。**過剰に付けない。\n\n")
        L.append("| 記事 | 前 | 後 | 公開状態 |\n|---|---|---|---|\n")
        for pid in TOEIC_POSTS:
            g = requests.get(f"{WP}/posts/{pid}", auth=AUTH, headers=UA,
                             verify=False, timeout=40)
            if g.status_code != 200:
                L.append(f"| {pid} | 取得できず | — | — |\n")
                continue
            j = g.json()
            before, st = j.get("categories", []), j.get("status")
            if DRY_RUN:
                L.append(f"| {pid} | {before} | [{tc['id']}]（DRY RUN） | {st} |\n")
                continue
            if before == [tc["id"]]:
                L.append(f"| {pid} | {before} | 変更なし（すでに割当済み） | {st} |\n")
                continue
            up = requests.post(f"{WP}/posts/{pid}", auth=AUTH, headers=UA,
                               verify=False, timeout=40,
                               json={"categories": [tc["id"]]})
            ok = up.status_code in (200, 201)
            L.append(f"| {pid} | {before} | "
                     f"{'✅ [' + str(tc['id']) + ']' if ok else '❌ ' + str(up.status_code)}"
                     f" | {st} |\n")
            print(f"[{pid}] {before} -> [{tc['id']}] {'OK' if ok else up.status_code}")

    # ── 2. 件数を取り直す。**ここでトップの表示が決まる** ──
    cats = get_cats()
    tc2 = cats.get("toeic-score", {})
    L.append(f"\n再取得したカテゴリ件数: `toeic-score` = **{tc2.get('count', 0)}本**"
             f" / `ai-english` = **{cats.get('ai-english', {}).get('count', 0)}本**\n\n")
    print("再取得 toeic-score:", tc2.get("count"))

    # ── 3. 記事一覧ページ（トップより先に作る）──────────
    L.append("## 3. 記事一覧ページ（トップより先に作る）\n\n")
    aid, amsg = ensure_page(pages, ARTICLES_SLUG, "記事一覧", ARTICLES_BODY)
    L.append(f"- slug `{ARTICLES_SLUG}` … {amsg}（ID {aid}）\n")
    L.append(f"- URL: {SITE}/{ARTICLES_SLUG}/\n\n")
    print(f"記事一覧: {amsg} id={aid}")

    # ── 4. トップページ（更新後の件数で作る）──────────
    L.append("## 4. トップページ\n\n")
    fid, fmsg = ensure_page(pages, FRONT_SLUG, "さくらの大人英語学び直しガイド",
                            front_body(cats))
    L.append(f"- slug `{FRONT_SLUG}` … {fmsg}（ID {fid}）\n\n")
    print(f"トップ: {fmsg} id={fid}")

    L.append("### カテゴリ導線（記事が0本のものはリンクにしない）\n\n")
    L.append("| カテゴリ | 記事数 | 扱い |\n|---|---|---|\n")
    for slug, label in ((CAT["学習法"], "英語学習法"),
                        ("toeic-score", "TOEIC・スコア"),
                        (CAT["比較"], "英会話サービス比較"),
                        (CAT["コーチング"], "英語コーチング"),
                        ("ai-english", "AI英語学習"),
                        (CAT["留学"], "海外留学・ワーホリ"),
                        ("philippines-cebu", "フィリピン・セブ留学"),
                        ("ryugaku-agent-cost", "留学エージェント・費用")):
        c = cats.get(slug)
        n = c.get("count", 0) if c else "（無し）"
        how = "リンクにする" if isinstance(n, int) and n > 0 else "**準備中（リンクなし）**"
        L.append(f"| {label} | {n} | {how} |\n")

    # ── 5. ホーム表示の切り替え ────────────────────
    L.append("\n## 5. ホーム表示の切り替え\n\n")
    if not (aid and fid):
        L.append("⚠️ ページIDが揃わないので**切り替えない**。\n")
    elif DRY_RUN:
        L.append(f"- `show_on_front` → `page` / `page_on_front` → {fid} / "
                 f"`page_for_posts` → {aid}\n\n→ （DRY RUN）\n")
    else:
        up = requests.post(f"{WP}/settings", auth=AUTH, headers=UA, verify=False,
                           timeout=40, json={"show_on_front": "page",
                                             "page_on_front": fid,
                                             "page_for_posts": aid})
        ok = up.status_code in (200, 201)
        L.append(f"- `show_on_front` → `page` / `page_on_front` → {fid} / "
                 f"`page_for_posts` → {aid}\n\n"
                 f"→ {'✅ 反映した' if ok else '❌ ' + str(up.status_code)}\n")

    # ── 6. プロフィール固定ページの監査 ──────────────
    L.append("\n## 6. プロフィール固定ページ\n\n")
    pr = next((x for x in pages if "プロフィール" in x["title"]["rendered"]), None)
    if not pr:
        L.append("見つからない\n")
    else:
        g = requests.get(f"{WP}/pages/{pr['id']}", auth=AUTH, headers=UA,
                         params={"context": "edit"}, verify=False, timeout=40)
        raw = g.json()["content"]["raw"] if g.status_code == 200 else ""
        (BK / day / f"page{pr['id']}_profile.json").write_text(
            json.dumps({"id": pr["id"], "content_raw": raw,
                        "title": g.json().get("title", {}).get("raw", "")},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        hits = [w for w in ("27歳", "営業事務", "5年後回し", "30歳まで",
                            "あと3年", "来年こそ", "ワーホリに行く", "挑戦記")
                if w in raw]
        L.append(f"- ID {pr['id']} / 旧設定の残存: "
                 f"**{'・'.join(hits) if hits else 'なし'}**\n")
        L.append(f"- バックアップ: `workspace/backups/{day}/page{pr['id']}_profile.json`\n")
        print(f"プロフィール ID {pr['id']} 旧設定: {hits}")
        if hits and not DRY_RUN:
            up = requests.post(f"{WP}/pages/{pr['id']}", auth=AUTH, headers=UA,
                               verify=False, timeout=60,
                               json={"content": PROFILE_BODY})
            L.append(f"- → {'✅ 差し替えた' if up.status_code in (200, 201) else '❌ ' + str(up.status_code)}\n")
        elif hits:
            L.append("- → 差し替える（DRY RUN）\n")

    # ── 7. 公開URLの確認 ─────────────────────────
    L.append("\n## 7. 公開URLの確認\n\n")
    L.append("| URL | HTTP | canonical | noindex | 判定 |\n|---|---|---|---|---|\n")
    for u in (f"{SITE}/", f"{SITE}/{FRONT_SLUG}/", f"{SITE}/{ARTICLES_SLUG}/",
              f"{SITE}/feed/"):
        try:
            r = requests.get(u, headers=UA, verify=False, timeout=45,
                             allow_redirects=True)
        except Exception as e:
            L.append(f"| {u} | エラー | — | — | {e} |\n")
            continue
        h = r.text if "html" in r.headers.get("Content-Type", "") else ""
        can = re.search(r'rel="canonical"[^>]+href="([^"]+)"', h)
        ni = "あり" if re.search(r'name="robots"[^>]+noindex', h, re.I) else "なし"
        canv = can.group(1) if can else "（無し）"
        note = ""
        if u.endswith(f"/{FRONT_SLUG}/"):
            if r.url.rstrip("/") == SITE:
                note = "✅ ルートへ301"
            elif canv.rstrip("/") == SITE:
                note = "✅ canonicalが / を指す"
            else:
                note = "⚠️ **重複の恐れ**。canonicalが / を指していない"
        L.append(f"| {u} | {r.status_code} | {canv} | {ni} | {note} |\n")
        print(f"{u} -> {r.status_code} canonical={canv} noindex={ni} {note}")

    # ── 8. 記事一覧が実際に記事を並べているか ─────────────
    # HTTP 200 だけでは「空の固定ページが表示されただけ」と区別が付かない。
    # 記事へのリンクを数えて、2ページ目まで辿れるかを見る。
    L.append("\n## 8. 記事一覧の中身とページ送り\n\n")
    hr = requests.get(f"{WP}/posts", auth=AUTH, headers=UA, verify=False,
                      timeout=40, params={"per_page": 1, "status": "publish"})
    n_posts = int(hr.headers.get("X-WP-Total", 0))
    per = int(settings.get("posts_per_page") or 10)
    pages_needed = -(-n_posts // per) if per else 1
    L.append(f"- 公開記事 **{n_posts}本** / 1ページ **{per}本** "
             f"→ 全 **{pages_needed}ページ** になるはず\n\n")

    L.append("| URL | HTTP | 記事リンク数 | 判定 |\n|---|---|---|---|\n")
    for label, u in (("1ページ目", f"{SITE}/{ARTICLES_SLUG}/"),
                     ("2ページ目", f"{SITE}/{ARTICLES_SLUG}/page/2/"),
                     ("存在しないページ", f"{SITE}/{ARTICLES_SLUG}/page/999/")):
        try:
            r = requests.get(u, headers=UA, verify=False, timeout=45)
        except Exception as e:
            L.append(f"| {label} {u} | エラー | — | {e} |\n")
            continue
        # 記事URLらしいリンクだけ数える（カテゴリ・タグ・固定ページは除く）
        links = set(re.findall(
            r'href="https://sakura-eigo\.com/([a-z0-9][a-z0-9\-]{6,})/"', r.text))
        links -= {ARTICLES_SLUG, FRONT_SLUG, "category", "tag", "author",
                  "privacy-policy", "contact", "profile"}
        n = len(links)
        if label == "存在しないページ":
            ok = "✅ 404を返す" if r.status_code == 404 else \
                 f"⚠️ {r.status_code}。空ページがインデックスされうる"
        elif label == "2ページ目":
            ok = ("✅ ページ送りが効いている" if r.status_code == 200 and n > 0
                  else ("— 2ページ目が不要（記事が1ページに収まる）"
                        if pages_needed < 2
                        else f"⚠️ 記事が並んでいない（HTTP {r.status_code}）"))
        else:
            ok = ("✅ 記事が並んでいる" if n >= min(per, n_posts)
                  else f"⚠️ **{n}本しか出ていない**。空の固定ページの可能性")
        L.append(f"| {label} {u} | {r.status_code} | {n} | {ok} |\n")
        print(f"{label} {u} -> {r.status_code} links={n} {ok}")

    (BK / day / "FRONTPAGE.md").write_text("".join(L), encoding="utf-8")
    print(f"\n→ workspace/backups/{day}/FRONTPAGE.md")


if __name__ == "__main__":
    main()
