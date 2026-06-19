#!/usr/bin/env python3
"""
fix_kanji_numerals.py
漢数字をアラビア数字に一括置換する。
DRY_RUN=true（デフォルト）では差分プレビューのみ保存。
"""
import os
from pathlib import Path
import requests, urllib3
urllib3.disable_warnings()

WP_BASE  = "https://sakura-eigo.com/wp-json/wp/v2"
WP_USER  = "rei.00pt2342@gmail.com"
WP_PASS  = os.environ.get("WP_APP_PASSWORD", "")
DRY_RUN  = os.environ.get("DRY_RUN", "true").lower() == "true"
POST_IDS = [int(x) for x in os.environ.get("POST_IDS", "117").split(",")]
OUT_DIR  = Path("affiliate-research-engine/playbook/workspace/kanji_fixes")

REPLACEMENTS = [
    ("三百六十五日",  "365日"),
    ("四万五千円",    "4万5,000円"),
    ("二千二百時間",  "2,200時間"),
    ("千二百時間",    "1,200時間"),
    ("三千時間",      "3,000時間"),
    ("千時間",        "1,000時間"),
    ("百時間",        "100時間"),
    ("二十七歳",  "27歳"),
    ("二十一歳",  "21歳"),
    ("三十歳",    "30歳"),
    ("二十四歳",  "24歳"),
    ("二十四時間",   "24時間"),
    ("一日三十分",   "1日30分"),
    ("一日三時間",   "1日3時間"),
    ("一日二時間",   "1日2時間"),
    ("一日一時間",   "1日1時間"),
    ("三十分",       "30分"),
    ("一〜三時間",   "1〜3時間"),
    ("二〜三時間",   "2〜3時間"),
    ("一〜二時間",   "1〜2時間"),
    ("三時間",    "3時間"),
    ("二時間目",  "2時間目"),
    ("二時間",    "2時間"),
    ("一時間目",  "1時間目"),
    ("一時間",    "1時間"),
    ("十年",  "10年"),
    ("五年",  "5年"),
    ("四年",  "4年"),
    ("三年",  "3年"),
    ("二年",  "2年"),
    ("一年",  "1年"),
    ("三日間",  "3日間"),
    ("四日目",  "4日目"),
    ("三日目",  "3日目"),
    ("三日",    "3日"),
    ("一日",    "1日"),
    ("三ヶ月",  "3ヶ月"),
    ("六ヶ月",  "6ヶ月"),
    ("一ヶ月",  "1ヶ月"),
    ("一週間",  "1週間"),
    ("二週間",  "2週間"),
    ("五人",    "5人"),
    ("三回",    "3回"),
    ("十回",    "10回"),
    ("二桁",    "2桁"),
    ("一円",    "1円"),
    ("五百点",  "500点"),
    ("四百点",  "400点"),
]

def apply_replacements(text):
    applied = []
    for old, new in REPLACEMENTS:
        if old in text:
            text = text.replace(old, new)
            applied.append((old, new))
    return text, applied

def get_post(post_id):
    r = requests.get(
        f"{WP_BASE}/posts/{post_id}",
        auth=(WP_USER, WP_PASS),
        headers={"User-Agent": "Mozilla/5.0"},
        verify=False, timeout=30,
    )
    return r.json() if r.status_code == 200 else None

def update_post(post_id, content):
    r = requests.post(
        f"{WP_BASE}/posts/{post_id}",
        auth=(WP_USER, WP_PASS),
        json={"content": content},
        headers={"User-Agent": "Mozilla/5.0"},
        verify=False, timeout=30,
    )
    return r.status_code in (200, 201)

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = [f"# Kanji Fix Report\nMode: {'DRY RUN' if DRY_RUN else 'LIVE'}\n\n"]

    for post_id in POST_IDS:
        print(f"\n[{post_id}] Fetching...")
        post = get_post(post_id)
        if not post:
            print("  ✗ Fetch failed")
            report.append(f"- [{post_id}] FETCH FAILED\n")
            continue

        title   = post["title"]["rendered"]
        content = post["content"]["rendered"]
        new_content, applied = apply_replacements(content)

        if not applied:
            print(f"  {title} → 漢数字なし、スキップ")
            report.append(f"- [{post_id}] {title} — NO CHANGES\n")
            continue

        print(f"  {title}")
        for old, new in applied:
            print(f"    {old} → {new}")

        (OUT_DIR / f"{post_id}_kanji_fixed.html").write_text(new_content, encoding="utf-8")

        if not DRY_RUN:
            ok = update_post(post_id, new_content)
            status = "✓ UPDATED" if ok else "✗ WP FAILED"
        else:
            status = "DRY RUN — preview saved"

        report.append(
            f"- [{post_id}] {title}\n"
            + "\n".join(f"  - `{o}` → `{n}`" for o, n in applied)
            + f"\n  → **{status}**\n\n"
        )
        print(f"  {status}")

    (OUT_DIR / "REPORT.md").write_text("".join(report), encoding="utf-8")
    print("\n✓ Done.")

if __name__ == "__main__":
    main()
