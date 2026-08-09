#!/usr/bin/env python3
"""
ai_eyecatch_prompts.py
AI英語学習6記事のアイキャッチ生成プロンプトを作り、
**文字カード型のまま予約されている5本を下書きへ戻す。**

いま設定されている画像は文字カード型で、
「文字だけのカード型は禁止」「白背景に記事タイトルを置いただけの画像は禁止」
に当てはまる。イラストを生成する環境がこちらに無いので、
**仮画像のまま公開・予約を続けない**という指示に従って止める。

  DRY_RUN=false python ai_eyecatch_prompts.py
出力: workspace/eyecatch-prompts/<記事ID>.md / backups/<日付>/AI_PAUSE.md
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings()
sys.path.insert(0, str(Path(__file__).parent))
import eyecatch_prompt as _ep

JST = timezone(timedelta(hours=9))
WP = "https://sakura-eigo.com/wp-json/wp/v2"
AUTH = ("rei.00pt2342@gmail.com", os.environ.get("WP_APP_PASSWORD", ""))
UA = {"User-Agent": "Mozilla/5.0"}
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"
BK = Path("affiliate-research-engine/playbook/workspace/backups")

CATEGORY = "AI英語学習"

# 画像内文言はタイトルから切り取らず、画像向けに書き直している。
# 場面と小物は6枚とも別にして、1枚ずつで記事が判別できるようにする
SPEC = [
    {
        "post": "993", "slug": "chatgpt-english-learning-steps",
        "title": "ChatGPTで英語学習を始める手順｜社会人が最初に試す3つの使い方",
        "lead": "ChatGPTに\n何をどう頼むか",
        "sub": "添削プロンプトの3つの型",
        "scene": ("Sakura sits at a small home desk in the evening, laptop "
                  "half-closed, holding a pen over an open paper notebook. "
                  "On the notebook three short handwritten lines are visible "
                  "as simple ruled marks (no readable words), each with a "
                  "small numbered circle 1, 2, 3 in the accent colour, "
                  "suggesting three prompt patterns. A warm desk lamp, a "
                  "cream mug, and a single sakura petal on the desk. No "
                  "screen content is shown on the laptop."),
        "alt": ("ChatGPTで英語学習を始めるときに使う、添削プロンプトの3つの型を"
                "ノートに書き出している場面"),
        "file": "eyecatch-chatgpt-english-learning-steps.png",
    },
    {
        "post": "995", "slug": "ai-eikaiwa-vs-online-eikaiwa",
        "title": "AI英会話とオンライン英会話の違い｜4つの軸で選ぶ",
        "lead": "AIと人、\nどちらから始める？",
        "sub": "4つの軸で選ぶ",
        "scene": ("Sakura stands beside a large hand-drawn comparison sheet "
                  "pinned to a light wall. The sheet has two blank columns "
                  "with simple icons at the top: a small robot face on the "
                  "left column and a simple person silhouette on the right "
                  "column, and four empty rows marked by small accent-colour "
                  "dots. She is tilting her head, comparing, one hand resting "
                  "on the edge of the sheet. No text inside the columns."),
        "alt": ("AI英会話と人の講師によるオンライン英会話を、4つの軸で並べて"
                "比べている場面"),
        "file": "eyecatch-ai-eikaiwa-vs-online-eikaiwa.png",
    },
    {
        "post": "997", "slug": "ai-translation-why-learn-english",
        "title": "AI翻訳があるのに英語を学ぶ意味｜場面で分けて考える",
        "lead": "AI翻訳があっても\n英語は必要？",
        "sub": "学ぶ範囲の決め方",
        "scene": ("Sakura is outdoors on a bright street, holding her phone "
                  "loosely at chest height with the screen turned away from "
                  "the viewer, while someone off-frame is mid-conversation "
                  "with her. A small hourglass icon floats near the phone in "
                  "the accent colour, suggesting waiting time. Her expression "
                  "is thoughtful, not troubled. Soft city background, blurred."),
        "alt": ("AI翻訳を開く待ち時間が問題になる場面と、そうでない場面を分けて"
                "考えている様子"),
        "file": "eyecatch-ai-translation-why-learn-english.png",
    },
    {
        "post": "999", "slug": "ai-pronunciation-app-how-to-choose",
        "title": "AI発音矯正アプリの選び方｜自動判定でできることと、できないこと",
        "lead": "発音の点数が出た。\nでも直し方は？",
        "sub": "選ぶときの4つの確認",
        "scene": ("Sakura wears simple over-ear headphones and holds a phone, "
                  "her other hand lightly touching her jaw as if checking how "
                  "she is producing a sound. Beside her floats a soft "
                  "sound-wave line in the accent colour with a small empty "
                  "circle at its centre, suggesting a score with nothing "
                  "written in it. Absolutely no digits anywhere."),
        "alt": ("発音の自動判定でできることと、点数だけでは決まらない直し方を"
                "分けて考えている場面"),
        "file": "eyecatch-ai-pronunciation-app-how-to-choose.png",
    },
    {
        "post": "1001", "slug": "ai-era-english-how-far",
        "title": "AI時代に必要な英語力はどこまでか｜場面から決める",
        "lead": "どこまでやれば\n足りるのか",
        "sub": "自分の場面から決める",
        "scene": ("Sakura sits cross-legged on the floor with four small "
                  "hand-drawn cards laid out in front of her in a row. Each "
                  "card carries only a simple icon: an open book, an ear, a "
                  "speech bubble, and a pen. Her hand is reaching to pick up "
                  "one card. The chosen card has a soft accent-colour glow. "
                  "No words on the cards."),
        "alt": ("読む・聞く・話す・書くの4つから、自分に必要な場面を1つ選んで"
                "いる場面"),
        "file": "eyecatch-ai-era-english-how-far.png",
    },
    {
        "post": "1003", "slug": "english-meeting-transcription-checklist",
        "title": "英語会議の文字起こしツールを選ぶ前に｜確認する5つのこと",
        "lead": "英語会議の\nAI文字起こし",
        "sub": "選ぶ前の5チェック",
        "scene": ("Sakura is at an office desk with a headset around her neck, "
                  "looking at a paper checklist with five empty checkboxes "
                  "marked in the accent colour. A closed laptop and a small "
                  "recorder-like device sit on the desk, both plain and "
                  "generic with no brand marks or visible screens. A window "
                  "with soft daylight behind her. Business-casual, calm."),
        "alt": ("英語会議の文字起こしツールを選ぶ前に確認する5つの項目を"
                "チェックリストで見ている場面"),
        "file": "eyecatch-english-meeting-transcription-checklist.png",
    },
]


def main():
    day = datetime.now(JST).strftime("%Y-%m-%d")
    (BK / day).mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    _ep.OUT.mkdir(parents=True, exist_ok=True)

    L = [f"# AI6記事：プロンプト作成と、予約の一時停止 {stamp}\n\n",
         f"モード: **{'DRY RUN（書いていない）' if DRY_RUN else 'LIVE（書いた）'}**\n\n",
         "いま設定されている画像は文字カード型で、「文字だけのカード型は禁止」に\n"
         "当てはまる。イラストを生成する環境がこちらに無いので、\n"
         "**仮画像のまま予約を続けず、下書きへ戻す。**\n\n",
         "| 記事 | 画像内文言 | 補助文言 | プロンプト | 前の状態 | 後の状態 |\n",
         "|---|---|---|---|---|---|\n"]

    for s in SPEC:
        path = _ep.OUT / f"{s['post']}.md"
        path.write_text(_ep.build(
            s["post"], s["slug"], s["title"], s["lead"], s["sub"],
            s["scene"], CATEGORY, s["alt"], s["file"]), encoding="utf-8")

        g = requests.get(f"{WP}/posts/{s['post']}", auth=AUTH, headers=UA,
                         params={"context": "edit"}, verify=False, timeout=45)
        before = g.json().get("status", "?") if g.status_code == 200 else "?"
        date_before = g.json().get("date", "") if g.status_code == 200 else ""

        after = before
        # 予約（future）だけを下書きへ戻す。公開済みの993は落とさない
        if before == "future":
            if DRY_RUN:
                after = "draft（DRY RUN）"
            else:
                (BK / day / f"ai_pause_{s['post']}.json").write_text(
                    json.dumps({"id": s["post"], "checked_at": stamp,
                                "status": before, "date": date_before},
                               ensure_ascii=False, indent=2), encoding="utf-8")
                u = requests.post(f"{WP}/posts/{s['post']}", auth=AUTH,
                                  headers=UA, verify=False, timeout=60,
                                  json={"status": "draft"})
                after = "draft" if u.status_code in (200, 201) \
                    else f"❌ {u.status_code}"
        elif before == "publish":
            after = "publish（優先差し替え。公開は止めない）"

        L.append(f"| {s['post']} | {s['lead'].replace(chr(10), ' / ')} | "
                 f"{s['sub']} | `eyecatch-prompts/{s['post']}.md` | "
                 f"{before} | {after} |\n")
        print(f"[{s['post']}] {before} → {after}")

    L.append("\n## 差し替えが済むまでの扱い\n\n"
             "- 予約5本は**下書き**。イラストを反映して検証が通ったら予約を戻す\n"
             "- 993は公開済み。**優先差し替え**の対象として残す\n"
             "- プロンプトの一時ファイルは、反映と検証が通ってから削除する\n"
             "- 失敗した場合は削除しない\n\n"
             "## 予約を戻すときの日時\n\n"
             "| 記事 | 元の予定 |\n|---|---|\n")
    for s in SPEC:
        f = BK / day / f"ai_pause_{s['post']}.json"
        if f.exists():
            d = json.loads(f.read_text())
            L.append(f"| {s['post']} | {d.get('date', '')} |\n")

    (BK / day / "AI_PAUSE.md").write_text("".join(L), encoding="utf-8")
    print(f"\n→ workspace/backups/{day}/AI_PAUSE.md")


if __name__ == "__main__":
    main()
