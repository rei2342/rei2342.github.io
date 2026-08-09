#!/usr/bin/env python3
"""
callan_publish.py
Callan記事（ID 647）を仕上げて公開する。

下書きの本文は監査を通っている（ブロッカー0）。
公開前に直すのは、本文以外の項目と、テンプレートのままの見出し。

  - スラッグが `calan-method-…` で綴りが違う → `callan-method-…`
  - H3「合わない人と、先に知っておきたい注意点」が他の29本と同じ文言だった
    （2026-08-09に全部を記事固有へ書き分けたので、ここも合わせる）
  - 抜粋（メタディスクリプション）が空
  - アイキャッチが無い
  - 英会話クラスタへの内部リンクが無い

  DRY_RUN=false python callan_publish.py
出力: workspace/backups/<日付>/callan/647.json / CALLAN_PUBLISH.md
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
UA = {"User-Agent": "Mozilla/5.0"}
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"
BK = Path("affiliate-research-engine/playbook/workspace/backups")
IMG = Path("affiliate-research-engine/playbook/workspace/seo/eyecatch_new")

PID = "647"
SLUG = "callan-method-three-things-check"
EXCERPT = ("カランメソッドの速さをうたう数字をいったん脇に置いて、"
           "自分に合うかを判断する3つの確認項目をまとめた。"
           "3秒で声に出せるかの自己診断まで持ち帰れる。")

# テンプレートのままだった見出しを、この記事が名指ししている条件へ
HEAD_OLD = "<h3>合わない人と、先に知っておきたい注意点</h3>"
HEAD_NEW = "<h3>自分のペースで考えたい人には、テンポが負担になる</h3>"

# 英会話クラスタへの内部リンク。647は「速いテンポで即答する形式」を扱うので、
# 話した量を測る273と、続かない理由を扱う546へ繋ぐ
LINKS = [
    ("546", "オンライン英会話が続かないのは、話し始めるまでの手数"),
    ("273", "1回のレッスンで話した秒数を測る"),
    ("287", "出席ではなく回収の数で測る"),
]
MARK_START = "<!-- internal-links:START -->"
MARK_END = "<!-- internal-links:END -->"

CHIP, L1, L2 = "確認項目", "カランメソッドを", "試す前に確かめる3つ"
ALT = ("カランメソッドを試す前に確認したい3つの項目。"
       "即答で詰まっているかを自分で確かめる")


def main():
    day = datetime.now(JST).strftime("%Y-%m-%d")
    (BK / day / "callan").mkdir(parents=True, exist_ok=True)
    IMG.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    L = [f"# Callan記事（647）の仕上げと公開 {stamp}\n\n",
         f"モード: **{'DRY RUN（書いていない）' if DRY_RUN else 'LIVE（書いた）'}**\n\n"]

    g = requests.get(f"{WP}/posts/{PID}", auth=AUTH, headers=UA,
                     params={"context": "edit"}, verify=False, timeout=45)
    if g.status_code != 200:
        print(f"取得できず {g.status_code}")
        return
    p = g.json()
    raw = p["content"]["raw"]
    (BK / day / "callan" / f"{PID}.json").write_text(json.dumps({
        "id": PID, "checked_at": stamp, "status": p["status"],
        "slug": p["slug"], "title": p["title"]["raw"],
        "excerpt": p["excerpt"]["raw"], "featured_media": p["featured_media"],
        "content_raw": raw}, ensure_ascii=False, indent=2), encoding="utf-8")

    # 公開前の確認。指示された項目を1つずつ見る
    checks = [
        ("「4倍速」が無い", "4倍速" not in raw),
        ("「350時間」「80時間」が無い",
         "350時間" not in raw and "80時間" not in raw),
        ("未確認の一人称の語りが無い",
         not _q.unverified_self_facts(raw)),
        ("QQ Englishの2項目に出典URLと確認日がある",
         raw.count("qqeng.com") >= 2 and raw.count("2026年8月9日時点") >= 2),
        ("見出しに第三者の成果数字が無い",
         not re.search(r'<h[23][^>]*>[^<]*[0-9]+[^<]*(?:倍|時間|点|割)',
                       raw)),
        ("CTAは記事で説明した案件だけ",
         len(re.findall(r'href="[^"]*(?:moshimo|a8\.net)[^"]*"', raw)) == 1
         and "4B9W9D+2IHWQA" in raw),
        ("PR表記がある", "アフィリエイトリンク" in raw),
        ("公開ゲートが通る", not _q.generation_blockers(raw)),
    ]
    L.append("## 公開前の確認\n\n| 項目 | 結果 |\n|---|---|\n")
    for name, ok in checks:
        L.append(f"| {name} | {'✅' if ok else '❌'} |\n")
    if not all(ok for _, ok in checks):
        L.append("\n**確認に落ちたので公開しない。**\n")
        (BK / day / "CALLAN_PUBLISH.md").write_text("".join(L),
                                                    encoding="utf-8")
        print("確認に落ちた。公開しない")
        return

    # 本文を直す
    new = raw
    if HEAD_OLD in new:
        new = new.replace(HEAD_OLD, HEAD_NEW, 1)
    if MARK_START not in new:
        items = ""
        for tid, label in LINKS:
            t = requests.get(f"{WP}/posts/{tid}", auth=AUTH, headers=UA,
                             verify=False, timeout=40)
            if t.status_code == 200:
                items += f'<li><a href="{t.json()["link"]}">{label}</a></li>\n'
        if items:
            block = (f"{MARK_START}\n<h2>あわせて確認したいもの</h2>\n"
                     f"<ul>\n{items}</ul>\n{MARK_END}")
            m = re.search(r"<p>※本記事にはアフィリエイトリンク", new)
            new = (new[:m.start()] + block + "\n" + new[m.start():]
                   if m else new + "\n" + block)

    blockers = _q.generation_blockers(new)
    if blockers:
        L.append(f"\n**書き換えた本文がゲートに掛かる: {blockers[0][:70]}**\n")
        (BK / day / "CALLAN_PUBLISH.md").write_text("".join(L),
                                                    encoding="utf-8")
        print("ゲートに掛かる")
        return

    # アイキャッチ
    mid = p["featured_media"]
    img = IMG / f"{PID}.png"
    _eb.build(PID, CHIP, L1, L2).save(img, "PNG", optimize=True)
    if not DRY_RUN and not mid:
        name = f"eyecatch-{PID}-{day.replace('-', '')}.png"
        up = requests.post(
            f"{WP}/media", auth=AUTH, verify=False, timeout=120,
            headers={**UA, "Content-Disposition":
                     f'attachment; filename="{name}"',
                     "Content-Type": "image/png"},
            data=img.read_bytes())
        if up.status_code in (200, 201):
            mid = up.json()["id"]
            requests.post(f"{WP}/media/{mid}", auth=AUTH, headers=UA,
                          verify=False, timeout=60,
                          json={"alt_text": ALT, "title": ALT[:60]})

    payload = {"content": new, "slug": SLUG, "excerpt": EXCERPT,
               "status": "publish"}
    if mid:
        payload["featured_media"] = mid

    L.append("\n## 変更\n\n| 項目 | 前 | 後 |\n|---|---|---|\n")
    L.append(f"| スラッグ | {p['slug']} | {SLUG} |\n")
    L.append(f"| 抜粋 | （空） | {EXCERPT[:40]}… |\n")
    L.append(f"| アイキャッチ | {p['featured_media']} | {mid or '（作れず）'} |\n")
    L.append(f"| 見出し | 合わない人と、先に知っておきたい注意点 | "
             f"{_q.strip_tags(HEAD_NEW)} |\n")
    L.append(f"| 内部リンク | 0本 | {len(LINKS)}本 |\n")
    L.append(f"| 状態 | {p['status']} | publish |\n")

    if DRY_RUN:
        L.append("\n（DRY RUN。書いていない）\n")
        print("DRY RUN")
    else:
        up = requests.post(f"{WP}/posts/{PID}", auth=AUTH, headers=UA,
                           verify=False, timeout=60, json=payload)
        ok = up.status_code in (200, 201)
        link = up.json().get("link", "") if ok else ""
        L.append(f"\n**{'✅ 公開した' if ok else '❌ ' + str(up.status_code)}**"
                 f" {link}\n")
        print(f"公開 {'OK' if ok else up.status_code} {link}")
        if ok:
            r = requests.get(link, headers=UA, verify=False, timeout=45)
            can = re.search(r'rel="canonical"[^>]+href="([^"]+)"', r.text)
            ni = bool(re.search(r'name="robots"[^>]+noindex', r.text, re.I))
            sd = 'application/ld+json' in r.text
            L.append(f"\n## 公開後\n\n| 項目 | 値 |\n|---|---|\n"
                     f"| HTTP | {r.status_code} |\n"
                     f"| canonical | {can.group(1) if can else '（無し）'} |\n"
                     f"| noindex | {'あり' if ni else 'なし'} |\n"
                     f"| 構造化データ | {'あり' if sd else '無し'} |\n")

    (BK / day / "CALLAN_PUBLISH.md").write_text("".join(L), encoding="utf-8")
    print(f"→ workspace/backups/{day}/CALLAN_PUBLISH.md")


if __name__ == "__main__":
    main()
