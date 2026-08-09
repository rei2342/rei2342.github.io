#!/usr/bin/env python3
"""
site_final_check.py
公開画面から確認できるものを、まとめて見る。

  サイト名 / キャッチフレーズ / トップ / 記事一覧 / プロフィール /
  ヘッダー / フッター / PC・スマホ / OGP / canonical / noindex /
  構造化データ / RSS / パンくず / カテゴリ導線 / 記事一覧への導線 / PR表記

ヘッダーに `/articles/` が無ければ、REST APIで足せるかを試す。
足せない場合は「手作業に残す」と書いて止める（勝手に別の方法へ回らない）。

  DRY_RUN=false python site_final_check.py
出力: workspace/seo/SITE_FINAL.md
"""
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

JST = timezone(timedelta(hours=9))
SITE = "https://sakura-eigo.com"
WP = f"{SITE}/wp-json/wp/v2"
AUTH = ("rei.00pt2342@gmail.com", os.environ.get("WP_APP_PASSWORD", ""))
PC = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) "
                     "Chrome/124.0 Safari/537.36")}
SP = {"User-Agent": ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
                     "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                     "Version/17.5 Mobile/15E148 Safari/604.1")}
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"
OUT = Path("affiliate-research-engine/playbook/workspace/seo")


def get(url, ua=PC):
    try:
        r = requests.get(url, headers=ua, verify=False, timeout=45)
        return r
    except Exception:
        return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    L = [f"# サイト外観の最終確認 {stamp}\n\n",
         f"モード: **{'DRY RUN' if DRY_RUN else 'LIVE'}**\n\n"]

    s = requests.get(f"{SITE}/wp-json/", headers=PC, verify=False, timeout=45)
    meta = s.json() if s.status_code == 200 else {}
    top = get(f"{SITE}/")
    arts = get(f"{SITE}/articles/")
    prof = get(f"{SITE}/profile/")
    sp = get(f"{SITE}/", SP)
    rss = get(f"{SITE}/feed/")
    smap = get(f"{SITE}/sitemap.xml") or get(f"{SITE}/wp-sitemap.xml")

    th = top.text if top else ""
    rows = [
        ("サイト名", meta.get("name", "（取得できず）")),
        ("キャッチフレーズ", meta.get("description") or "（空）"),
        ("トップページ", f"HTTP {top.status_code}" if top else "取得できず"),
        ("記事一覧 /articles/", f"HTTP {arts.status_code}" if arts else "取得できず"),
        ("プロフィール /profile/", f"HTTP {prof.status_code}" if prof else "取得できず"),
        # f式の中にバックスラッシュを書くと Python 3.11 では構文エラーになる。
        # viewport の判定は先に外へ出す
        ("スマホ表示",
         f"HTTP {sp.status_code}・viewport "
         + ("あり" if sp and 'name="viewport"' in sp.text else "なし")
         if sp else "取得できず"),
        ("RSS", f"HTTP {rss.status_code}・"
                f"{rss.text.count('<item>')}件" if rss else "取得できず"),
        ("サイトマップ", f"HTTP {smap.status_code}" if smap else "取得できず"),
    ]
    for k, v in [
        ("OGP画像", bool(re.search(r'property="og:image"', th))),
        ("OGPタイトル", bool(re.search(r'property="og:title"', th))),
        ("canonical", bool(re.search(r'rel="canonical"', th))),
        ("noindex（トップに付いていないこと）",
         not re.search(r'name="robots"[^>]+noindex', th, re.I)),
        ("構造化データ", 'application/ld+json' in th),
        ("パンくず", bool(re.search(r'breadcrumb', th, re.I))),
        ("ヘッダーメニュー", bool(re.search(r'<(?:nav|header)', th, re.I))),
        ("フッター", bool(re.search(r'<footer', th, re.I))),
        ("記事一覧への導線（トップ）", "/articles" in th),
        ("カテゴリ導線（トップ）", bool(re.search(r'/category/', th))),
        ("「準備中」がトップに残っていないこと", "準備中" not in th),
    ]:
        rows.append((k, "✅" if v else "❌"))

    L.append("| 項目 | 結果 |\n|---|---|\n")
    for k, v in rows:
        L.append(f"| {k} | {v} |\n")

    # PR表記が全記事にあるか
    posts = requests.get(f"{WP}/posts", headers=PC, verify=False, timeout=60,
                         params={"per_page": 100, "status": "publish",
                                 "_fields": "id,content"})
    pl = posts.json() if posts.status_code == 200 else []
    nopr = [str(p["id"]) for p in pl
            if "アフィリエイトリンク" not in p["content"]["rendered"]
            and re.search(r'moshimo|a8\.net', p["content"]["rendered"])]
    L.append(f"| PR表記が無いのにCTAがある記事 | "
             f"{('❌ ' + ' '.join(nopr)) if nopr else '✅ 0本'} |\n")

    # ヘッダーに /articles/ を足せるか
    L.append("\n## ヘッダーメニューの `/articles/`\n\n")
    if "/articles" in re.sub(r'(?s)<footer.*?</footer>', '', th):
        L.append("トップページのヘッダー側に `/articles` へのリンクがある。**対応不要**。\n")
    else:
        m = requests.get(f"{SITE}/wp-json/wp/v2/menus", auth=AUTH, headers=PC,
                         verify=False, timeout=45)
        if m.status_code != 200:
            L.append(f"REST APIのメニュー機能が使えない（HTTP {m.status_code}）。\n"
                     "**WordPress管理画面でしか操作できないので、手作業へ残す。**\n")
        else:
            menus = m.json()
            L.append(f"メニュー {len(menus)}件: "
                     f"{', '.join(x['name'] for x in menus) or '（無し）'}\n\n")
            if not menus:
                L.append("**メニューが1件も無い。管理画面で作る必要があるので手作業へ残す。**\n")
            elif DRY_RUN:
                L.append("（DRY RUN。足していない）\n")
            else:
                mid = menus[0]["id"]
                r = requests.post(
                    f"{SITE}/wp-json/wp/v2/menu-items", auth=AUTH, headers=PC,
                    verify=False, timeout=45,
                    json={"title": "記事一覧", "url": f"{SITE}/articles/",
                          "menus": mid, "status": "publish", "type": "custom"})
                L.append(f"追加: HTTP {r.status_code} "
                         f"{'✅' if r.status_code in (200, 201) else '❌ 手作業へ残す'}\n")

    (OUT / "SITE_FINAL.md").write_text("".join(L), encoding="utf-8")
    for k, v in rows:
        print(f"  {k}: {v}")
    print(f"\n→ workspace/seo/SITE_FINAL.md")


if __name__ == "__main__":
    main()
