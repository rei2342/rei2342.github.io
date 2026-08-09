#!/usr/bin/env python3
"""
href_repair.py
本文の中の**自サイトへのリンクが、実在する記事URLと一致しているか**を見る。

クロールで記事526から1件だけ「リダイレクト経由」が出た。
中身は日本語スラッグの記事へのリンクで、URLが途中で切れていた。
WordPressが推測して正しい記事へ飛ばしてくれるので404にはならず、
外形からは気づけない。**リダイレクトは切れかけたリンクの前触れ**なので直す。

やること:
  1. 公開記事のURL一覧を作る
  2. 各記事の本文から自サイトへのリンクを取り出す
  3. 一覧に無いものを拾い、**実在URLの頭が一致するなら**切れたURLと判定する
  4. 補って書き戻す（本文の他の場所には触らない）

頭が一致しないものは自動で直さない。一覧に出して人が見る。

  DRY_RUN=false python href_repair.py
出力: workspace/backups/<日付>/hrefs/<id>.json / HREF_REPAIR.md
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

import requests
import urllib3

urllib3.disable_warnings()
sys.path.insert(0, str(Path(__file__).parent))
import wp_audit as _wa

JST = timezone(timedelta(hours=9))
WP = "https://sakura-eigo.com/wp-json/wp/v2"
AUTH = ("rei.00pt2342@gmail.com", os.environ.get("WP_APP_PASSWORD", ""))
UA = {"User-Agent": "Mozilla/5.0"}
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"
BK = Path("affiliate-research-engine/playbook/workspace/backups")

SITE = "sakura-eigo.com"
# 記事ではない行き先。ここへのリンクは対象外
NOT_A_POST = re.compile(
    r"/wp-(?:admin|content|json|includes)/|/articles/?$|/profile/?$|"
    r"/privacy/?$|/contact/?$|/start/?$|^https?://sakura-eigo\.com/?$", re.I)


def norm(u):
    s = urlsplit(u)
    return f"{s.scheme}://{s.netloc}{s.path.rstrip('/')}/".lower()


def main():
    day = datetime.now(JST).strftime("%Y-%m-%d")
    (BK / day / "hrefs").mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")

    posts = _wa.published()
    url_by_norm = {norm(p["link"]): p["link"] for p in posts}
    id_by_norm = {norm(p["link"]): str(p["id"]) for p in posts}
    print(f"公開記事 {len(posts)}本")

    rows = []
    for p in sorted(posts, key=lambda x: x["id"]):
        pid = str(p["id"])
        g = requests.get(f"{WP}/posts/{pid}", auth=AUTH, headers=UA,
                         params={"context": "edit"}, verify=False, timeout=45)
        if g.status_code != 200:
            rows.append({"post_id": pid, "href": "", "verdict": "取得できず",
                         "fixed_to": "", "result": str(g.status_code)})
            continue
        raw = g.json()["content"]["raw"]
        new = raw
        found = []
        for m in re.finditer(r'href="(https?://[^"]*sakura-eigo\.com[^"]*)"',
                             raw):
            href = m.group(1)
            if NOT_A_POST.search(href):
                continue
            n = norm(href)
            if n in url_by_norm:
                found.append((href, "一致", ""))
                continue
            # 実在URLの頭と一致するなら、途中で切れたURL
            cand = [full for k, full in url_by_norm.items()
                    if k.startswith(n.rstrip("/"))]
            if len(cand) == 1:
                found.append((href, "URLが途中で切れている", cand[0]))
                new = new.replace(f'href="{href}"', f'href="{cand[0]}"')
            else:
                found.append((href, "実在しないURL（自動で直さない）", ""))

        bad = [f for f in found if f[1] != "一致"]
        if not bad:
            continue

        (BK / day / "hrefs" / f"{pid}.json").write_text(
            json.dumps({"id": pid, "checked_at": stamp, "content_raw": raw},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        fixable = new != raw
        result = "（DRY RUN）"
        if fixable and not DRY_RUN:
            up = requests.post(f"{WP}/posts/{pid}", auth=AUTH, headers=UA,
                               verify=False, timeout=60,
                               json={"content": new})
            result = "✅" if up.status_code in (200, 201) else \
                f"❌ {up.status_code}"
        elif not fixable:
            result = "手で直す"
        for href, verdict, to in bad:
            rows.append({
                "post_id": pid, "href": unquote(href), "verdict": verdict,
                "fixed_to": f"{id_by_norm.get(norm(to), '')} {unquote(to)}"
                            if to else "",
                "result": result})
        print(f"[{pid}] 直すリンク {len(bad)}件 {result}")

    L = [f"# 自サイトへのリンクの点検 {stamp}\n\n",
         f"モード: **{'DRY RUN（書いていない）' if DRY_RUN else 'LIVE（書いた）'}**\n\n",
         f"公開 **{len(posts)}本**の本文から、自サイトへのリンクを全部取り出して、\n"
         "実在する記事URLと突き合わせた。\n\n",
         f"- 直したリンク: **{sum(1 for r in rows if r['fixed_to'])}件**\n",
         f"- 自動で直せないもの: **{sum(1 for r in rows if not r['fixed_to'] and r['verdict'] != '取得できず')}件**\n\n",
         "| 記事 | 本文に書いてあるURL | 判定 | 直した先 | 結果 |\n",
         "|---|---|---|---|---|\n"]
    for r in rows:
        L.append(f"| {r['post_id']} | {r['href'][:60]} | {r['verdict']} | "
                 f"{r['fixed_to'][:60]} | {r['result']} |\n")
    if not rows:
        L.append("| — | — | すべて実在URLと一致 | — | — |\n")
    (BK / day / "HREF_REPAIR.md").write_text("".join(L), encoding="utf-8")
    print(f"\n{len(rows)}件 → workspace/backups/{day}/HREF_REPAIR.md")


if __name__ == "__main__":
    main()
