#!/usr/bin/env python3
"""
market_research.py
市場調査のうち、**外向きの通信が要るぶんだけ**を取りに行く。

  python market_research.py 272,149,23        # 記事IDを指定
  python market_research.py all               # SERPの控えにある全記事

取るもの
  1. SERP上位10件のページ構造（型・冒頭の答え・H2・比較軸・独自要素・CTA）
  2. 記事が使っている案件の公式一次情報（料金・無料期間・条件・確認日）

**記事を書き換えない。WordPressへ触らない。**
書くのは workspace/market/ の下だけ。

なぜ別スクリプトなのか
  開発コンテナは外向きのHTTPが全部遮断されている（curl も 403 を返す）。
  取れるのは検索サービスの結果だけで、ページ本文は取れない。
  Actions には通信があるので、そちらで走らせる。

  Actions での呼び方（新しいワークフローを既定ブランチへ入れる前でも動く）:
    rewrite-uploader.yml を workflow_dispatch し、
    TARGET_IDS に `ops:market:272,149` を渡す
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JST = timezone(timedelta(hours=9))
SERP_DIR = ROOT / "workspace/market/serp"
OFFICIAL_DIR = ROOT / "workspace/market/official"

UA = {"User-Agent": "Mozilla/5.0 (compatible; sakura-market-research/1.0)"}
TIMEOUT = 30

# 公式一次情報を取りに行く先。**案件ごとに1つ。**
# ここに無いものは「未取得」と書く。**推測で埋めない**
OFFICIAL = {
    "speek": "https://www.speek.jp/",
    "sptr": "https://sptr.jp/",
    "nativecamp": "https://nativecamp.net/",
    "nativecamp_ryugaku": "https://nativecamp.net/ryugaku",
    "johokan": "https://www.ryugaku-johokan.com/",
    "phil_navi": "https://philippines-university.jp/",
    "qq_english": "https://www.qqeng.com/",
    "dmm": "https://eikaiwa.dmm.com/",
    "rarejob": "https://www.rarejob.com/",
    "sapuri_nichijo": "https://eigosapuri.jp/",
    "cebridge": "https://cebridge.jp/",
    "ugaku": "https://u-gaku.jp/",
}

# 公式ページから拾う条件。**拾えなかったものは None のまま残す**
COND = [
    ("price", r"月額\s*([0-9,]+)\s*円|([0-9,]+)\s*円\s*/\s*月"),
    ("free_period", r"([0-9]+)\s*日間?\s*無料|無料体験\s*([0-9]+)\s*回"),
    ("count", r"回数無制限|([0-9]+)\s*回\s*/\s*月"),
]


def now():
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def get(url):
    """1ページ取る。**落ちても止まらない。** 落ちた事実を返す。"""
    import requests
    try:
        r = requests.get(url, headers=UA, timeout=TIMEOUT)
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"
        r.encoding = r.apparent_encoding or r.encoding
        return r.text, None
    except Exception as e:                              # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def text_of(html):
    html = re.sub(r"(?is)<(script|style|nav|footer)[^>]*>.*?</\1>", " ", html)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def headings(html):
    """H2/H3 の見出し。**構造だけ。本文は保存しない。**"""
    out = []
    for m in re.finditer(r"(?is)<h([23])[^>]*>(.*?)</h\1>", html):
        t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(2))).strip()
        if t and len(t) < 80:
            out.append(f"H{m.group(1)}: {t}")
    return out[:30]


def unique_elements(html):
    """表・計算機・診断・一次調査・画像があるか。**中身は取らない。**"""
    out = []
    if re.search(r"(?i)<table", html):
        out.append(f"表 {len(re.findall(r'(?i)<table', html))}個")
    if re.search(r"(?i)<input|calculator|シミュレー|計算機", html):
        out.append("入力欄か計算機")
    if re.search(r"診断|チェックリスト", html):
        out.append("診断・チェックリスト")
    if re.search(r"独自調査|アンケート|n\s*=\s*[0-9]+", html):
        out.append("一次調査")
    n = len(re.findall(r"(?i)<img", html))
    if n:
        out.append(f"画像 {n}枚")
    return out


def cta_info(html):
    """CTAの位置と訴求。**文言はそのまま保存しない。**要約だけ。"""
    body = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    total = max(len(body), 1)
    out = []
    for m in re.finditer(r'(?is)<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', body):
        label = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if not re.search(r"無料|申し込|体験|相談|見積|カウンセリング|資料",
                         label):
            continue
        out.append({"position_pct": round(m.start() / total * 100),
                    "pitch": re.findall(
                        r"無料|申し込|体験|相談|見積|カウンセリング|資料",
                        label)[:3],
                    "label_len": len(label)})
    return out[:8]


def updated_shown(text):
    m = re.search(r"(20[0-9]{2})[年/\-.]\s*([0-9]{1,2})[月/\-.]\s*"
                  r"([0-9]{1,2})", text[:4000])
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" \
        if m else None


def article_type(text, heads):
    joined = " ".join(heads) + " " + text[:1500]
    for name, pat in (("料金", r"費用|料金|いくら"),
                      ("比較", r"比較|おすすめ|選[3-9]|ランキング"),
                      ("体験", r"体験談|受講した|使ってみた"),
                      ("FAQ", r"よくある質問|Q&A|知恵袋"),
                      ("手順", r"やり方|手順|方法|ステップ|コツ")):
        if re.search(pat, joined):
            return name
    return "不明"


def scan_serp(pid, rec):
    """SERPの各ページを開いて、構造だけ取る。**本文は保存しない。**"""
    out = []
    for row in rec.get("serp", []):
        url = row.get("url")
        if not url:
            out.append(dict(row, fetch="URLが控えに無い"))
            continue
        html, err = get(url)
        if err:
            out.append(dict(row, fetch=f"取得できない（{err}）"))
            continue
        txt = text_of(html)
        heads = headings(html)
        out.append(dict(
            row,
            fetch="取得",
            fetched_at=now(),
            updated_shown=updated_shown(txt),
            article_type=article_type(txt, heads),
            lead_answer=txt[:180],          # 冒頭の要旨。**引用の範囲**
            headings=heads,
            unique_elements=unique_elements(html),
            cta=cta_info(html)))
        print(f"  [{pid}] {row.get('domain')} → {out[-1]['fetch']}")
    return out


def scan_official(slugs):
    """公式の料金・無料期間・条件。**取れなかったら None のまま。**"""
    out = {}
    for slug in slugs:
        url = OFFICIAL.get(slug)
        if not url:
            out[slug] = {"status": "取得先が未登録", "url": None}
            continue
        html, err = get(url)
        if err:
            out[slug] = {"status": f"取得できない（{err}）", "url": url,
                         "fetched_at": now()}
            continue
        txt = text_of(html)
        rec = {"status": "取得", "url": url, "fetched_at": now(),
               "recheck_on": (datetime.now(JST) + timedelta(days=7)
                              ).strftime("%Y-%m-%d")}
        for key, pat in COND:
            m = re.search(pat, txt)
            rec[key] = next((g for g in m.groups() if g), m.group(0)) \
                if m else None
        # 出典の確認用に、条件の周辺だけを控える
        m = re.search(r"[^。]{0,60}(無料|料金|月額)[^。]{0,60}。", txt)
        rec["quote"] = m.group(0)[:160] if m else None
        out[slug] = rec
        print(f"  公式 {slug} → {rec['status']}")
    return out


def main(arg):
    import yaml
    src = sorted(SERP_DIR.glob("*.yaml"))
    if not src:
        print("SERPの控えが無い。先に検索結果を保存する")
        sys.exit(1)
        return
    data = yaml.safe_load(src[-1].read_text(encoding="utf-8"))
    want = ([str(x) for x in data["articles"]] if arg in ("all", "")
            else [x.strip() for x in arg.split(",") if x.strip()])

    stamp = datetime.now(JST).strftime("%Y-%m-%d")
    full, slugs = {}, set()
    for pid in want:
        rec = data["articles"].get(int(pid)) or data["articles"].get(pid)
        if not rec:
            print(f"[{pid}] 控えに無い。飛ばす")
            continue
        print(f"[{pid}] {rec['query']}")
        full[pid] = {"query": rec["query"], "serp": scan_serp(pid, rec)}
    for slug in OFFICIAL:
        slugs.add(slug)

    SERP_DIR.mkdir(parents=True, exist_ok=True)
    OFFICIAL_DIR.mkdir(parents=True, exist_ok=True)
    p1 = SERP_DIR / f"{stamp}_full.yaml"
    p1.write_text(yaml.safe_dump(
        {"fetched_at": now(), "note": "本文は保存していない。構造だけ",
         "articles": full}, allow_unicode=True, sort_keys=False, width=200),
        encoding="utf-8")
    p2 = OFFICIAL_DIR / f"{stamp}.yaml"
    p2.write_text(yaml.safe_dump(
        {"fetched_at": now(),
         "rule": "取れなかった項目は None。**0として扱わない**",
         "programs": scan_official(sorted(slugs))},
        allow_unicode=True, sort_keys=False, width=200), encoding="utf-8")
    print(f"\n→ {p1}\n→ {p2}")
    print("**記事もWordPressも触っていない。**")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "all")
