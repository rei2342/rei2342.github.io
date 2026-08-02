#!/usr/bin/env python3
"""
title_rewriter.py
公開済み・下書きの記事タイトルを「勝ち型」に書き換える。

2026-08-01の検証で、150字級の抽象・反論エッセイ型タイトルは
表示は取れてもクリックが0だった。勝っていたのは短い一人称＋数字＋引き算型。
  例: TOEIC 600点で2年止まった私が、やめた3つのことと、やり直した1つのこと

スラッグ（URL）は変更しないのでリンクは切れない。タイトルのみ差し替える。
DRY_RUN=true（既定）で提案だけ出し、false で実際にWPを更新する。
"""
import os
import re
import time
from pathlib import Path

import requests
import anthropic
import urllib3

urllib3.disable_warnings()

WP_BASE = "https://sakura-eigo.com/wp-json/wp/v2"
WP_USER = "rei.00pt2342@gmail.com"
WP_PASS = os.environ.get("WP_APP_PASSWORD", "")
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"
OUT_DIR = Path("affiliate-research-engine/playbook/workspace/title_rewrites")

# これ以下の長さのタイトルは既に勝ち型とみなして触らない
KEEP_UNDER = int(os.environ.get("KEEP_UNDER", "56"))

# 内部メモは対象外
SKIP_MARKS = ("【Threads用】", "【メモ】", "【社内")

CLAUDE = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

PROMPT = """あなたは田中さくら（27歳・営業事務・東京）。英語を5年後回しにしてきて、過去にスクールで4.5万円を溶かした。

下の記事につける新しいタイトルを1つ作って。

現在のタイトル: {title}

記事本文（冒頭）:
{excerpt}

【必ず守る型】2026-08-01の検証で最も反応が良かった型を踏襲する。
・30〜45字。長くても50字を超えない
・一人称（私 / 27歳の私 など）を入れる
・**その記事の本文に固有の数字**を必ず1つ以上入れる（点数・年数・金額・回数・時間）
・できれば引き算フレーム（やめたN個のこと / 捨てた / 減らした）を使う
・読者の「あ、私だ」を作る。共感（あなたのせいでなく型のせい）が伝わる言葉にする

【重要：使い回し禁止】
・「4.5万円を溶かした」というスクール失敗の話は**全記事に共通するプロフィール**なので、
  タイトルには原則使わない。記事一覧に並んだとき全部同じ顔になり、テンプレ臭が出て逆効果。
  その記事だけが持つ数字（TOEICの点数、留学費用、レッスン時間、期間など）を主役にする
・「溶かした」「気づいた」「わかった」を毎回使わない。記事ごとに動詞を変える
・書き出しを毎回「27歳の私が」にしない。数字から始める／状況から始める等、変化をつける

【禁止】
・150字級の抽象・反論エッセイ型（「〜で並ぶ記事はどれも…だが…のほうだ」型）は絶対に使わない
・「——」（emダッシュ）を使わない
・漢数字を使わない（27歳・3ヶ月・15万 のようにアラビア数字）
・記事に書かれていない数字や事実をでっち上げない
・煽り・誇大・断定（「必ず」「絶対に伸びる」等）を使わない
・末尾に句点（。）を付けない
・金額の表記を混ぜない（45000円ではなく4.5万円のように、記事本文の書き方に合わせる）

新しいタイトルだけを1行で出力して。説明・かぎ括弧・前置きは不要。"""


def get_all_posts():
    posts, page = [], 1
    while True:
        r = requests.get(
            f"{WP_BASE}/posts",
            auth=(WP_USER, WP_PASS),
            params={
                "per_page": 100,
                "page": page,
                "status": "publish,draft,pending,future,private",
                "_fields": "id,title,content,status,slug",
            },
            headers={"User-Agent": "Mozilla/5.0"},
            verify=False,
            timeout=30,
        )
        if r.status_code != 200:
            break
        batch = r.json()
        if not batch:
            break
        posts += batch
        if len(batch) < 100:
            break
        page += 1
    return posts


def update_title(post_id, new_title):
    r = requests.post(
        f"{WP_BASE}/posts/{post_id}",
        auth=(WP_USER, WP_PASS),
        json={"title": new_title},          # slug は送らないのでURLは変わらない
        headers={"User-Agent": "Mozilla/5.0"},
        verify=False,
        timeout=30,
    )
    return r.status_code in (200, 201)


def strip_html(html):
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&[a-z]+;|&#\d+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def make_title(title, excerpt):
    msg = CLAUDE.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": PROMPT.format(title=title, excerpt=excerpt)}],
    )
    out = msg.content[0].text.strip()
    out = out.split("\n")[0].strip().strip('"')
    # タイトル全体が「」で囲まれている場合だけ外す。
    # 無条件に strip すると本文中の正当な引用符（例: 「意味ない」を5回検索）まで
    # 剥がれて片方だけ残るので、対応が取れている場合に限る。
    if out.startswith("「") and out.endswith("」") and out.count("「") == 1:
        out = out[1:-1]
    out = out.replace("——", "、").replace("—", "、")
    return out.rstrip("。.")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = [f"# Title Rewrite Report\nMode: {'DRY RUN' if DRY_RUN else 'LIVE'}\n"
              f"対象: {KEEP_UNDER}字を超えるタイトル\n\n"]

    posts = get_all_posts()
    print(f"取得: {len(posts)}件")

    changed = skipped = failed = 0

    for p in posts:
        pid = p["id"]
        title = p["title"]["rendered"]
        status = p.get("status", "")

        if any(m in title for m in SKIP_MARKS):
            print(f"[{pid}] スキップ（内部メモ）")
            report.append(f"- [{pid}] {title[:40]} — SKIPPED (内部メモ)\n")
            skipped += 1
            continue

        if len(title) <= KEEP_UNDER:
            print(f"[{pid}] スキップ（既に短い {len(title)}字）")
            report.append(f"- [{pid}] ({len(title)}字) {title} — SKIPPED (既に勝ち型)\n")
            skipped += 1
            continue

        excerpt = strip_html(p.get("content", {}).get("rendered", ""))[:1500]

        try:
            new_title = make_title(title, excerpt)
        except Exception as e:
            print(f"[{pid}] ✗ 生成エラー: {e}")
            report.append(f"- [{pid}] ERROR: {e}\n")
            failed += 1
            continue

        if not new_title or len(new_title) > 70:
            print(f"[{pid}] ✗ 不採用（{len(new_title)}字）: {new_title}")
            report.append(f"- [{pid}] REJECTED ({len(new_title)}字): {new_title}\n")
            failed += 1
            continue

        print(f"[{pid}] {status}")
        print(f"   旧({len(title)}字): {title[:60]}")
        print(f"   新({len(new_title)}字): {new_title}")

        report.append(
            f"\n### [{pid}] ({status})\n"
            f"- 旧 ({len(title)}字): {title}\n"
            f"- **新 ({len(new_title)}字): {new_title}**\n"
        )

        if not DRY_RUN:
            if update_title(pid, new_title):
                print("   ✓ 更新")
                report.append("- 更新: OK\n")
                changed += 1
            else:
                print("   ✗ 更新失敗")
                report.append("- 更新: FAILED\n")
                failed += 1
            time.sleep(1)
        else:
            changed += 1

    summary = f"\n## 集計\n- 書き換え: {changed}件\n- スキップ: {skipped}件\n- 失敗: {failed}件\n"
    print(summary)
    report.append(summary)
    (OUT_DIR / "REPORT.md").write_text("".join(report), encoding="utf-8")


if __name__ == "__main__":
    main()
