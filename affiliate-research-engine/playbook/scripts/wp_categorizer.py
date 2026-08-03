#!/usr/bin/env python3
"""
wp_categorizer.py
記事のトピック分類にもとづいて、WordPressのカテゴリを設定する。

affiliate_inserter.classify() が返すトピック（philippines / workingholiday /
coaching …）を、サイトに実在するカテゴリへ対応づける。
カテゴリはWP側の名前・スラッグに部分一致で寄せるので、
サイトのカテゴリ名が変わっても壊れにくい。

MODE=list  … 実在するカテゴリを一覧するだけ（設定は変えない）
MODE=apply … TARGET_IDS の記事にカテゴリを設定する
"""
import os
import re
import sys
import time
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings()

sys.path.insert(0, str(Path(__file__).parent))
import affiliate_inserter as _ai

WP_BASE = "https://sakura-eigo.com/wp-json/wp/v2"
WP_USER = "rei.00pt2342@gmail.com"
WP_PASS = os.environ.get("WP_APP_PASSWORD", "")
MODE = os.environ.get("MODE", "list")
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"
OUT = Path("affiliate-research-engine/playbook/workspace/categories")

# トピック → カテゴリ名。キーは affiliate_inserter.TOPIC_MAP と同じものを使う。
# 部分一致で推測させると default が「英語コーチング」に吸われるなど事故るので、
# サイトに実在する4カテゴリへ明示的に対応づける。
# 47本を4カテゴリに寄せると「海外留学・ワーホリ」だけ21本になり偏る。
# 留学系を3つに割ると 13/11/7/6/5/4 と均等になり、
# カテゴリと主力案件が1対1で対応する（ネイティブキャンプ留学＝留学3種）。
TOPIC_CATEGORY = {
    "philippines":    "フィリピン・セブ留学",
    "workingholiday": "海外留学・ワーホリ",
    "study_abroad":   "海外留学・ワーホリ",
    "agent":          "留学エージェント・費用",
    "domestic":       "留学エージェント・費用",
    "coaching":       "英語コーチング",
    "toeic":          "英語学習法",
    "pronunciation":  "英語学習法",
    "training":       "英語学習法",
    "eikaiwa":        "英会話サービス比較",
    "default":        "英語学習法",
}

# 無ければ作るカテゴリ。既存のものはリネームしないので、
# アーカイブのURLは変わらず、空になる旧カテゴリも出ない。
NEW_CATEGORIES = [
    ("フィリピン・セブ留学",   "philippines-cebu"),
    ("留学エージェント・費用", "ryugaku-agent-cost"),
]


def get_categories():
    r = requests.get(
        f"{WP_BASE}/categories",
        auth=(WP_USER, WP_PASS),
        params={"per_page": 100, "_fields": "id,name,slug,count,parent"},
        headers={"User-Agent": "Mozilla/5.0"},
        verify=False,
        timeout=30,
    )
    return r.json() if r.status_code == 200 else []


def create_category(name, slug):
    r = requests.post(
        f"{WP_BASE}/categories",
        auth=(WP_USER, WP_PASS),
        json={"name": name, "slug": slug},
        headers={"User-Agent": "Mozilla/5.0"},
        verify=False,
        timeout=30,
    )
    if r.status_code in (200, 201):
        return r.json()
    # 既に同名/同スラッグがある場合はWPが term_exists を返す
    if r.status_code == 400:
        data = r.json()
        existing = data.get("data", {}).get("term_id")
        if existing:
            return {"id": existing, "name": name, "slug": slug, "count": 0}
    print(f"   ✗ カテゴリ作成失敗 HTTP {r.status_code}: {r.text[:160]}")
    return None


def ensure_categories(cats):
    """設計に必要なカテゴリが無ければ作る。既存はそのまま使う。"""
    have = {c["name"] for c in cats}
    for name, slug in NEW_CATEGORIES:
        if name in have:
            continue
        # list モードは「見るだけ」なので、実際の作成は apply のときだけ行う
        if DRY_RUN or MODE != "apply":
            # ドライランでも割り当て先が見えるよう仮のIDで並べる。
            # 実際に設定するのはLIVEのときだけなので影響はない。
            print(f"  + 作成予定: {name} (slug={slug})")
            cats.append({"id": -1, "name": name, "slug": slug, "count": 0})
            continue
        c = create_category(name, slug)
        if c:
            print(f"  + 作成: {name} (id={c['id']})")
            cats.append(c)
    return cats


def pick_category(topic, cats):
    """トピックに対応するカテゴリを返す。見つからなければ None（設定しない）。"""
    want = TOPIC_CATEGORY.get(topic)
    if not want:
        return None
    for c in cats:
        if c["name"] == want:
            return c
    # カテゴリ名が変更された場合の保険。前方一致で拾う。
    for c in cats:
        if want[:4] in c["name"]:
            return c
    return None


def get_post(post_id):
    r = requests.get(
        f"{WP_BASE}/posts/{post_id}",
        auth=(WP_USER, WP_PASS),
        params={"_fields": "id,title,categories,content"},
        headers={"User-Agent": "Mozilla/5.0"},
        verify=False,
        timeout=30,
    )
    return r.json() if r.status_code == 200 else None


def classify_post(post):
    """タイトルで判定し、決まらなければ本文で判定する。

    classify() はタイトルだけを見るが、2026-08-02にタイトルを
    「短い一人称＋数字」型へ書き換えた結果、判定に使うキーワード
    （フィリピン・ワーホリ等）がタイトルから消えた。
    本文には残っているので、既定値に落ちたときは本文で見直す。
    """
    title = post["title"]["rendered"]
    body = post.get("content", {}).get("rendered", "")
    by_title = _ai.classify(title)
    topic = _ai.classify_full(title, body)
    return topic, ("タイトル" if topic == by_title else "本文で補正")


def set_category(post_id, cat_id):
    r = requests.post(
        f"{WP_BASE}/posts/{post_id}",
        auth=(WP_USER, WP_PASS),
        json={"categories": [cat_id]},
        headers={"User-Agent": "Mozilla/5.0"},
        verify=False,
        timeout=30,
    )
    return r.status_code in (200, 201)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cats = get_categories()
    if not cats:
        print("カテゴリを取得できなかった")
        sys.exit(1)

    print("設計に必要なカテゴリを確認:")
    cats = ensure_categories(cats)
    print()

    lines = ["# WordPress カテゴリ一覧\n\n",
             "| ID | 名前 | スラッグ | 記事数 |\n|---|---|---|---|\n"]
    print(f"カテゴリ {len(cats)}件:")
    for c in sorted(cats, key=lambda x: -x["count"]):
        print(f"  [{c['id']:>3}] {c['name']}  (slug={c['slug']}, {c['count']}本)")
        lines.append(f"| {c['id']} | {c['name']} | {c['slug']} | {c['count']} |\n")

    lines.append("\n## トピック→カテゴリの対応\n\n")
    lines.append("| トピック | 割り当て先 |\n|---|---|\n")
    print("\nトピック→カテゴリの対応:")
    for topic in TOPIC_CATEGORY:
        c = pick_category(topic, cats)
        label = f"{c['name']} (id={c['id']})" if c else "該当なし（設定しない）"
        print(f"  {topic:16} → {label}")
        lines.append(f"| {topic} | {label} |\n")

    (OUT / "CATEGORIES.md").write_text("".join(lines), encoding="utf-8")

    if MODE != "apply":
        return

    ids = [int(x) for x in os.environ.get("TARGET_IDS", "").replace(" ", "").split(",") if x]
    if not ids:
        print("\nTARGET_IDS が空。設定対象がない。")
        return

    print(f"\n{'DRY RUN' if DRY_RUN else 'LIVE'} — {len(ids)}件にカテゴリを設定")
    report = [f"# Category Assign Report\nMode: {'DRY RUN' if DRY_RUN else 'LIVE'}\n\n"]
    ok = skip = fail = 0

    for pid in ids:
        post = get_post(pid)
        if not post:
            print(f"[{pid}] ✗ 取得失敗")
            report.append(f"- [{pid}] FETCH FAILED\n")
            fail += 1
            continue

        title = post["title"]["rendered"]
        topic, src = classify_post(post)
        cat = pick_category(topic, cats)

        if not cat:
            print(f"[{pid}] − 該当カテゴリなし（topic={topic}）")
            report.append(f"- [{pid}] SKIPPED 該当なし (topic={topic})\n")
            skip += 1
            continue

        if post.get("categories") == [cat["id"]]:
            print(f"[{pid}] − すでに「{cat['name']}」")
            report.append(f"- [{pid}] 変更なし（{cat['name']}）\n")
            skip += 1
            continue

        print(f"[{pid}] {title[:34]} → {cat['name']} (topic={topic}/{src})")
        report.append(
            f"- [{pid}] {title[:40]} → **{cat['name']}** (topic={topic}, 判定={src})\n")

        if DRY_RUN:
            ok += 1
            continue

        if set_category(pid, cat["id"]):
            print("   ✓ 設定")
            ok += 1
        else:
            print("   ✗ 失敗")
            report.append(f"- [{pid}] SET FAILED\n")
            fail += 1
        time.sleep(1)

    summary = f"\n## 集計\n- 設定: {ok}件\n- スキップ: {skip}件\n- 失敗: {fail}件\n"
    print(summary)
    report.append(summary)
    (OUT / "ASSIGN_REPORT.md").write_text("".join(report), encoding="utf-8")


if __name__ == "__main__":
    main()
