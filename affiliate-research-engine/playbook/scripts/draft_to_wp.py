#!/usr/bin/env python3
"""
draft_to_wp.py
workspace/drafts/ のMarkdown下書きを WordPress に下書きとして上げる。

日次生成の投稿処理は日付ファイル名に依存していて、
定説記事のような別名のドラフトを上げられなかった。
ファイルを指定して同じ処理を通せるようにする。

CTA挿入・スラッグ生成・カテゴリ設定まで日次と同じ経路を使う。
"""
import os
import re
import sys
from pathlib import Path

import markdown2
import requests
import urllib3

urllib3.disable_warnings()

sys.path.insert(0, str(Path(__file__).parent))
import affiliate_inserter as _ai
import wp_categorizer as _wc

WP_BASE = "https://sakura-eigo.com/wp-json/wp/v2"
WP_USER = "rei.00pt2342@gmail.com"
WP_PASS = os.environ.get("WP_APP_PASSWORD", "")
DRAFT = os.environ.get("DRAFT_FILE", "")
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"


def make_slug(title):
    try:
        import anthropic
        ai = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        msg = ai.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=40,
            messages=[{"role": "user", "content":
                       "次の日本語記事タイトルを、SEOに適した短い英語スラッグにして。"
                       "ルール: 半角小文字英数字とハイフンのみ / 3〜6語 / 内容を表す / "
                       "説明や引用符なしでスラッグだけ出力。\n"
                       f"タイトル: {title}"}],
        )
        s = re.sub(r"[^a-z0-9\-]+", "-", msg.content[0].text.strip().lower()).strip("-")
        return s[:60]
    except Exception as e:
        print(f"スラッグ生成に失敗（WPの自動生成に任せる）: {e}")
        return ""


def main():
    if not DRAFT or not Path(DRAFT).exists():
        print(f"下書きが見つからない: {DRAFT}")
        sys.exit(1)

    raw = Path(DRAFT).read_text(encoding="utf-8")

    title, content = "Draft", raw
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            fm = raw[:end + 4]
            m = re.search(r"^title:\s*(.+)$", fm, re.MULTILINE)
            if m:
                title = m.group(1).strip()
            content = raw[end + 4:].lstrip("\n")
    if title == "Draft":
        m = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if m:
            title = m.group(1).strip()

    # 本文冒頭のH1はWP側のタイトルと重複するので落とす
    content = re.sub(r"^#\s+.+\n?", "", content, count=1).lstrip("\n")
    content = re.split(r"^###?\s*(SERP分析メモ|調査メモ)", content,
                       maxsplit=1, flags=re.MULTILINE)[0].rstrip()

    html = markdown2.markdown(content, extras=["fenced-code-blocks", "tables",
                                               "break-on-newline"])

    topic = _ai.classify_full(title, html)
    cta, progs = _ai.build_cta(topic)
    html = _ai.strip_box(html) + cta

    text_len = len(re.sub(r"<[^>]+>", "", _ai.strip_box(html)))
    print(f"タイトル: {title}")
    print(f"本文: {text_len}字 / トピック: {topic} / 案件: {progs}")

    payload = {"title": title, "content": html, "status": "draft"}

    slug = make_slug(title)
    if slug:
        payload["slug"] = slug
        print(f"スラッグ: {slug}")

    cats = _wc.get_categories()
    cat = _wc.pick_category(topic, cats)
    if cat:
        payload["categories"] = [cat["id"]]
        print(f"カテゴリ: {cat['name']}")

    if DRY_RUN:
        print("\nDRY RUN のため投稿しない")
        return

    r = requests.post(f"{WP_BASE}/posts", auth=(WP_USER, WP_PASS), json=payload,
                      headers={"User-Agent": "Mozilla/5.0"}, verify=False, timeout=60)
    if r.status_code in (200, 201):
        d = r.json()
        print(f"\n下書きを作成: id={d.get('id')} / {d.get('link')}")
    else:
        print(f"\n失敗 HTTP {r.status_code}: {r.text[:300]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
