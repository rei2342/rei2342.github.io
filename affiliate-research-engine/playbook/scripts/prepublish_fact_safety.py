#!/usr/bin/env python3
"""
prepublish_fact_safety.py
前日22:00に、翌日07:00公開予定の予約記事だけを検査する。

★通知だけ。WordPressは一切書き換えない。
  自動下書き化・自動公開解除・本文自動修正はしない。
  誤検知で公開が止まると翌朝まで誰も気づかない。
  下書きへ戻す判断は、記事の中身を読める人がする。

★なぜ前日22:00なのか
  予約公開は WordPress側の cron が実行するので、公開の直前をフックできない。
  さらに GitHub Actions の schedule は実測で毎回 68〜98分 遅れる（2026-08 実測）。
  06:00 指定では 07:00 の公開に間に合わないことがある。
  締切から離すほうが確実なので、前日22:00に翌朝ぶんを見る（猶予9時間）。

出力: workspace/reports/prepublish/<公開予定日>.md
      PASSのときは何も書かない（毎晩「異常なし」が並ぶと本物の警告が埋もれる）
"""
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings()

JST = timezone(timedelta(hours=9))
SITE = "https://sakura-eigo.com"
WP = f"{SITE}/wp-json/wp/v2"
AUTH = ("rei.00pt2342@gmail.com", os.environ.get("WP_APP_PASSWORD", ""))
OUT = Path(__file__).resolve().parents[1] / "workspace" / "reports" / "prepublish"

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"

# ━━━ Fact Safety（market_intelligence/services/note_fact_safety.py と同じ規則）
_FIRST_PERSON = re.compile(r"私|自分|僕|(?<!の)うち")
_PERSONAL_ACT = re.compile(
    r"(?:払っ(?:た(?!ら|り)|ていた|てきた|続け)|支払っ(?:た(?!ら|り)|ていた)|"
    r"通っ(?:た(?!ら|り)|ていた)|受け(?:た(?!ら|り)|ていた|続け)|"
    r"やめ(?:た(?!ら|り)|ていた)|脱落し(?:た(?!ら|り))|挫折し(?:た(?!ら|り))|"
    r"取っ(?:た(?!ら|り))|買っ(?:た(?!ら|り))|申し込[んみ](?:だ|ました))")
_NUMBER = re.compile(r"\d[\d,\.]*\s*(?:円|万|点|％|%|週間|ヶ月|か月|年|社|回|日)")
_HIGH_HINT = re.compile(r"歳|TOEIC|点|万円|円")

_A_HREF = re.compile(r'<a\b[^>]*href\s*=\s*["\']([^"\']+)["\']', re.I)
_ASP = re.compile(r"px\.a8\.net|a8\.net|af\.moshimo\.com|moshimo|valuecommerce|"
                  r"accesstrade|rentracks|felmat|link-ag", re.I)
_PR = re.compile(r"PRを含み|広告を含み|アフィリエイト.{0,6}(?:含|利用)|プロモーションを含")
_NOINDEX = re.compile(r"noindex", re.I)
_CANON = re.compile(r'rel\s*=\s*["\']canonical["\'][^>]*href\s*=\s*["\']([^"\']+)', re.I)
_CHECKED_AT = re.compile(r"20\d{2}\s*[-/年]\s*\d{1,2}\s*[-/月]\s*\d{1,2}")
_NEEDS_SOURCE = re.compile(r"\d[\d,]*\s*円|\d+\s*%|\d+\s*割|料金|価格|平均\s*\d|統計|調査によ")
_TAG = re.compile(r"<[^>]+>")
_SENT = re.compile(r"[^。！？\n]+[。！？]?")


def to_text(html):
    h = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html or "", flags=re.S | re.I)
    return re.sub(r"\s+", " ", _TAG.sub(" ", h)).strip()


def fact_safety(text, has_affiliate):
    """HIGH / MEDIUM を返す。★一人称かつ具体的な行為・数値だけを拾う。"""
    high, med = [], []
    for s in _SENT.findall(text):
        s = s.strip()
        if not s or not _FIRST_PERSON.search(s):
            continue
        if not _PERSONAL_ACT.search(s):
            continue
        if _NUMBER.search(s) and _HIGH_HINT.search(s):
            high.append(s)
        else:
            med.append(s)
    return high, med


def head_status(u):
    try:
        r = requests.head(u, timeout=15, allow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0 prepublish"})
        if r.status_code >= 400:              # HEAD を拒む先があるので GET で確かめ直す
            r = requests.get(u, timeout=20, allow_redirects=True, stream=True,
                             headers={"User-Agent": "Mozilla/5.0 prepublish"})
        return r.status_code
    except Exception:
        return None


def check(post):
    html = (post.get("content") or {}).get("raw") or \
           (post.get("content") or {}).get("rendered") or ""
    title = (post.get("title") or {}).get("raw") or \
            (post.get("title") or {}).get("rendered") or ""
    text = to_text(html)
    hrefs = _A_HREF.findall(html)
    ext = [h for h in hrefs if h.startswith("http")]
    has_aff = any(_ASP.search(h) for h in hrefs)
    has_pr = bool(_PR.search(text))
    out = []

    def add(name, ok, detail, excerpt=""):
        out.append((name, PASS if ok else FAIL, detail, excerpt))

    high, med = fact_safety(text, has_aff)
    add("fact_safety_high", not high, f"HIGH {len(high)}件", high[0][:90] if high else "")
    add("fact_safety_medium", not med, f"MEDIUM {len(med)}件", med[0][:90] if med else "")

    if _NEEDS_SOURCE.search(text):
        add("verified_source", bool(ext), f"料金・制度・統計あり／出典URL {len(ext)}本")
        add("source_checked_at", bool(_CHECKED_AT.search(text)), "確認日の記載")
    else:
        out.append(("verified_source", SKIP, "料金・制度・統計の記述なし", ""))
        out.append(("source_checked_at", SKIP, "同上", ""))

    if has_aff and not has_pr:
        add("pr_affiliate_consistency", False, "アフィリリンクがあるのにPR表記が無い")
    elif has_pr and not has_aff:
        add("pr_affiliate_consistency", False,
            "PR表記があるのにアフィリリンクが0本（付けすぎも不整合）")
    else:
        add("pr_affiliate_consistency", True,
            f"リンク{'あり' if has_aff else 'なし'}／PR表記{'あり' if has_pr else 'なし'}")

    words = [w for w in re.split(r"[、。「」『』（）\s,.\-—…？！?!]+", title) if len(w) >= 3]
    hit = sum(1 for w in words if w in text)
    add("title_body_match", (not words) or hit >= max(1, len(words) // 2),
        f"タイトル語 {hit}/{len(words)} が本文にある", title[:70])

    if ext:
        bad = [(u, c) for u, c in ((u, head_status(u)) for u in ext) if c is None or c >= 400]
        add("outbound_links", not bad, f"外部{len(ext)}本中 {len(bad)}本が失敗",
            "" if not bad else f"{bad[0][0][:80]} → {bad[0][1]}")
    else:
        out.append(("outbound_links", SKIP, "外部リンクなし", ""))

    add("featured_image", bool(post.get("featured_media")), "アイキャッチ")
    add("category", bool(post.get("categories")), "カテゴリ")

    m = _CANON.search(html)
    if m:
        add("canonical", (post.get("slug") or "") in m.group(1),
            f"本文canonical: {m.group(1)[:70]}")
    else:
        out.append(("canonical", SKIP, "本文にcanonicalなし（WordPressがheadで出す。正常）", ""))
    add("noindex_absence", not _NOINDEX.search(html), "本文にnoindexが無いこと")
    return title, out


def main():
    now = datetime.now(JST)
    target = (now.date() + timedelta(days=1)).isoformat()
    print(f"[prepublish] 実行 {now.isoformat(timespec='seconds')} / 対象公開日 {target}")

    r = requests.get(f"{WP}/posts", auth=AUTH, timeout=30,
                     params={"status": "future", "per_page": 100, "context": "edit"})
    if r.status_code >= 400:
        print(f"[prepublish] 予約記事を取得できません: HTTP {r.status_code}")
        sys.exit(1)
    posts = [p for p in r.json() if (p.get("date") or "")[:10] == target]
    print(f"[prepublish] {target} 公開予定 {len(posts)}本")

    failed = []
    for p in posts:
        title, res = check(p)
        ng = [x for x in res if x[1] == FAIL]
        mark = "FAIL" if ng else "PASS"
        print(f"  #{p['id']} [{mark}] {p.get('date')} {title[:44]}")
        for name, st, detail, ex in res:
            if st == FAIL:
                print(f"      ★{name}: {detail}" + (f" 「{ex}」" if ex else ""))
        if ng:
            failed.append((p, title, ng))

    if not failed:
        # ★PASSのときは何も出さない。ファイルも作らない。
        print("[prepublish] 全てPASS。通知は出しません")
        return

    OUT.mkdir(parents=True, exist_ok=True)
    lines = [f"# 予約公開の前日検査 — {target} 07:00 公開予定", "",
             f"検査時刻: {now.isoformat(timespec='seconds')}",
             f"対象 {len(posts)}本 / FAIL {len(failed)}本", "",
             "★自動では何もしていません。下書きへ戻すか、直して予約し直すかは人が決めてください。", ""]
    for p, title, ng in failed:
        lines += [f"## #{p['id']} {title}", f"- 公開予定: {p.get('date')}",
                  f"- {p.get('link', '')}", ""]
        for name, st, detail, ex in ng:
            lines.append(f"- **{name}**: {detail}" + (f"\n    - 「{ex}」" if ex else ""))
        lines.append("")
    (OUT / f"{target}.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[prepublish] HUMAN_ACTION_REQUIRED: {len(failed)}本  → "
          f"workspace/reports/prepublish/{target}.md")


if __name__ == "__main__":
    main()
