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

# トピック → カテゴリを探すためのキーワード（優先順）。
# WP側のカテゴリ名/スラッグにこの語が含まれていれば、それを使う。
TOPIC_KEYWORDS = {
    "philippines":   ["フィリピン", "セブ", "philippin", "cebu", "留学"],
    "workingholiday": ["ワーホリ", "ワーキングホリデー", "working", "holiday", "留学"],
    "agent_general": ["エージェント", "留学", "agent"],
    "agent_free":    ["エージェント", "留学", "agent"],
    "coaching":      ["コーチング", "coaching", "スクール"],
    "toeic":         ["TOEIC", "toeic", "スコア", "試験"],
    "training":      ["アプリ", "教材", "トレーニング", "学習", "勉強"],
    "habit":         ["継続", "習慣", "オンライン英会話", "英会話"],
    "work_english":  ["ビジネス", "仕事", "business"],
    "hours_2000":    ["学習", "勉強", "時間"],
    "cost":          ["費用", "お金", "料金", "cost"],
    "default":       ["英語", "学習", "勉強"],
}


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


def pick_category(topic, cats):
    """トピックに最も合うカテゴリを選ぶ。見つからなければ None。"""
    for kw in TOPIC_KEYWORDS.get(topic, []):
        low = kw.lower()
        for c in cats:
            if low in c["name"].lower() or low in c["slug"].lower():
                return c
    return None


def get_post(post_id):
    r = requests.get(
        f"{WP_BASE}/posts/{post_id}",
        auth=(WP_USER, WP_PASS),
        params={"_fields": "id,title,categories"},
        headers={"User-Agent": "Mozilla/5.0"},
        verify=False,
        timeout=30,
    )
    return r.json() if r.status_code == 200 else None


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

    lines = ["# WordPress カテゴリ一覧\n\n",
             "| ID | 名前 | スラッグ | 記事数 |\n|---|---|---|---|\n"]
    print(f"実在するカテゴリ {len(cats)}件:")
    for c in sorted(cats, key=lambda x: -x["count"]):
        print(f"  [{c['id']:>3}] {c['name']}  (slug={c['slug']}, {c['count']}本)")
        lines.append(f"| {c['id']} | {c['name']} | {c['slug']} | {c['count']} |\n")

    lines.append("\n## トピック→カテゴリの対応\n\n")
    lines.append("| トピック | 割り当て先 |\n|---|---|\n")
    print("\nトピック→カテゴリの対応:")
    for topic in TOPIC_KEYWORDS:
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
        topic = _ai.classify(title)
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

        print(f"[{pid}] {title[:34]} → {cat['name']} (topic={topic})")
        report.append(f"- [{pid}] {title[:40]} → **{cat['name']}** (topic={topic})\n")

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
