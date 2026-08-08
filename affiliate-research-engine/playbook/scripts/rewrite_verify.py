#!/usr/bin/env python3
"""
rewrite_verify.py
反映したあと、記事が壊れていないかを外から確かめる。

見るもの: HTTP / タイトル / 見出し構造 / 文字化け / CTAとリンク先 /
         非表示にしたCTA / 目次 / canonical / noindex / ゲート再実行

出力: workspace/backups/<日付>/VERIFY.md
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

JST = timezone(timedelta(hours=9))
WP_BASE = "https://sakura-eigo.com/wp-json/wp/v2"
WP_USER = "rei.00pt2342@gmail.com"
WP_PASS = os.environ.get("WP_APP_PASSWORD", "")
POSTS = [x.strip() for x in os.environ.get("POSTS", "").split(",") if x.strip()]
SRC = Path("affiliate-research-engine/playbook/workspace/claims/rewrites")
BK = Path("affiliate-research-engine/playbook/workspace/backups")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0"}

MOJIBAKE = re.compile(r"[ï¿½]|â€|ã|&amp;amp;")


def main():
    day = datetime.now(JST).strftime("%Y-%m-%d")
    ids = POSTS or [f.stem for f in SRC.glob("*.html")]
    L = [f"# 反映後の検証 {datetime.now(JST).strftime('%Y-%m-%d %H:%M:%S JST')}\n\n"]
    bad = 0

    for pid in ids:
        r = requests.get(f"{WP_BASE}/posts/{pid}", auth=(WP_USER, WP_PASS),
                         params={"context": "edit"}, headers=UA,
                         verify=False, timeout=40)
        if r.status_code != 200:
            L.append(f"\n## ❌ 記事 {pid} … API {r.status_code}\n")
            bad += 1
            continue
        p = r.json()
        raw = p["content"]["raw"]
        url = p.get("link", "")
        title = (p.get("title") or {}).get("raw", "")

        pub = requests.get(url, headers=UA, verify=False, timeout=45,
                           allow_redirects=True)
        html = pub.text if pub.status_code == 200 else ""

        issues = []
        if pub.status_code != 200:
            issues.append(f"HTTP {pub.status_code}")
        if title and title not in html:
            issues.append("タイトルが公開ページに出ていない")
        if MOJIBAKE.search(_q.strip_tags(raw)):
            issues.append("文字化けの疑い")
        if raw.count("<h2") == 0:
            issues.append("H2が0本")
        for tag in ("p", "h2", "h3", "a"):
            if raw.count(f"<{tag}") - raw.count(f"</{tag}") not in (0,):
                issues.append(f"<{tag}> の開閉が合わない")
        g = _q.generation_blockers(raw)
        if g:
            issues.append(f"draft_gate 不合格 {len(g)}件")
        c = _q.cta_claim_gate(raw)
        if c:
            issues.append(f"cta_claim_gate 不合格 {len(c)}件")

        can = re.search(r'<link[^>]+rel="canonical"[^>]+href="([^"]+)"', html)
        noindex = bool(re.search(r'<meta[^>]+name="robots"[^>]+noindex', html, re.I))
        xrobots = pub.headers.get("X-Robots-Tag", "")
        toc = "ez-toc" in html or "toc_widget" in html or "目次" in html
        hidden = len(re.findall(r"<!-- cta-hidden:START", raw))
        ctas = re.findall(r'href="([^"]*(?:af\.moshimo\.com|px\.a8\.net)[^"]*)"', raw)

        if noindex:
            issues.append("**noindex が付いている**")
        if "noindex" in xrobots.lower():
            issues.append(f"**X-Robots-Tag: {xrobots}**")
        if can and can.group(1).rstrip("/") != url.rstrip("/"):
            issues.append(f"canonical が別URL: {can.group(1)}")

        mark = "✅" if not issues else "⚠️"
        if issues:
            bad += 1
        L.append(f"\n---\n\n## {mark} 記事 {pid}｜{title}\n\n{url}\n\n")
        L.append(f"- HTTP: {pub.status_code} / 本文 {len(_q.strip_tags(raw))}字\n")
        L.append(f"- H2 {raw.count('<h2')}本 / H3 {raw.count('<h3')}本\n")
        L.append(f"- CTA {len(ctas)}本 / 非表示にしたCTA {hidden}箇所\n")
        L.append(f"- canonical: {can.group(1) if can else '（無し）'}\n")
        L.append(f"- noindex: {'あり' if noindex else 'なし'} / "
                 f"X-Robots-Tag: {xrobots or 'なし'}\n")
        L.append(f"- 目次: {'あり' if toc else 'なし'}\n")
        L.append(f"- draft_gate: {'通過' if not g else '不合格'} / "
                 f"cta_claim_gate: {'通過' if not c else '不合格'}\n")
        for u in sorted(set(ctas)):
            L.append(f"  - CTA: `{u[:90]}`\n")
        if issues:
            L.append("\n**要対応**\n\n" + "".join(f"- {i}\n" for i in issues))
        print(f"[{pid}] {mark} {' / '.join(issues) if issues else 'OK'}")

    (BK / day).mkdir(parents=True, exist_ok=True)
    (BK / day / "VERIFY.md").write_text("".join(L), encoding="utf-8")
    print(f"\n要対応 {bad}/{len(ids)}本 → workspace/backups/{day}/VERIFY.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
