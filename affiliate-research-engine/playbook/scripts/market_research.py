#!/usr/bin/env python3
"""
market_research.py
市場調査のうち、**外向きの通信が要るぶんだけ**を取りに行く。

  python market_research.py 272,149,23        # 記事IDを指定
  python market_research.py all               # SERPの控えにある全記事

取るもの
  1. SERP（locale=ja-JP / country=JP / モバイルとデスクトップを分けて取得）
     広告・動画・ショッピング・強調スニペット・自然検索を**枠ごとに分ける**。
     自然検索が10件に満たなくても、**取れた件数のまま完了する。**
     並び番号は `observed_order`。**掲載順位ではない**
  2. 取れた自然検索のページ構造（型・冒頭の答え・H2・独自要素・CTA）
  3. 対象記事が本文で扱っている案件だけの公式一次情報

やらないこと
  - Googleを直接スクレイピングしない（規約と安定性。取得サービス経由）
  - 件数を10へ合わせない
  - **本文が取れないとき、検索スニペットで埋めない**
  - 同一ドメインの重複を消さない（別に記録する）

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

# ── SERPの取得条件。**この条件を控えへ必ず書く** ──────
# 取得サービスは環境変数で選ぶ。**Googleを直接スクレイピングしない**
# （利用規約に触れるうえ、壊れやすい）。鍵が無ければ「取得不能」と書く
SERP_LOCALE = "ja-JP"
SERP_COUNTRY = "JP"
SERP_DEVICES = ["mobile", "desktop"]
# 区別して記録する枠。**混ぜない**
RESULT_TYPES = ["organic", "ad", "video", "shopping", "featured_snippet",
                "people_also_ask", "other"]


def serp_provider():
    """使える取得サービスを返す。無ければ None。**推測で埋めない。**"""
    if os.environ.get("SERPAPI_KEY"):
        return "serpapi"
    if os.environ.get("BING_SEARCH_KEY"):
        return "bing"
    return None


def fetch_serp(query, device):
    """1クエリ・1デバイスぶん取る。

    返すのは (results, meta)。results は枠ごとに分けた辞書の配列で、
    **自然検索が10件に満たなくても、取れた件数のまま返す。**
    足りない分を他の枠やスニペットで埋めない。
    """
    prov = serp_provider()
    at = now()
    base = {"query": query, "locale": SERP_LOCALE, "country": SERP_COUNTRY,
            "device": device, "provider": prov, "fetched_at": at}
    if not prov:
        return [], dict(base, status="取得不能",
                        why="SERPAPI_KEY も BING_SEARCH_KEY も無い。"
                            "**Googleを直接取得しない**（規約と安定性）。"
                            "鍵をSecretsへ入れてから回す")
    if prov == "serpapi":
        import requests
        r = requests.get("https://serpapi.com/search", timeout=TIMEOUT,
                         params={"q": query, "hl": "ja", "gl": "jp",
                                 "google_domain": "google.co.jp",
                                 "device": device, "num": 10,
                                 "api_key": os.environ["SERPAPI_KEY"]})
        if r.status_code != 200:
            return [], dict(base, status="取得不能",
                            why=f"HTTP {r.status_code}")
        d = r.json()
        out = []
        for i, x in enumerate(d.get("organic_results") or [], 1):
            out.append({"result_type": "organic", "observed_order": i,
                        "url": x.get("link"), "title": x.get("title"),
                        "domain": (x.get("link") or "").split("/")[2:3],
                        "displayed_date": x.get("date")})
        for key, t in (("ads", "ad"), ("inline_videos", "video"),
                       ("shopping_results", "shopping"),
                       ("related_questions", "people_also_ask")):
            for x in (d.get(key) or []):
                out.append({"result_type": t, "observed_order": None,
                            "url": x.get("link"), "title": x.get("title")})
        if d.get("answer_box"):
            out.append({"result_type": "featured_snippet",
                        "observed_order": 0,
                        "url": d["answer_box"].get("link"),
                        "title": d["answer_box"].get("title")})
        return out, dict(base, status="取得",
                         organic_count=sum(1 for x in out
                                           if x["result_type"] == "organic"))
    # bing は枠の内訳が取れない。**取れないことを書く**
    import requests
    r = requests.get("https://api.bing.microsoft.com/v7.0/search",
                     headers={"Ocp-Apim-Subscription-Key":
                              os.environ["BING_SEARCH_KEY"]},
                     params={"q": query, "mkt": "ja-JP", "count": 10},
                     timeout=TIMEOUT)
    if r.status_code != 200:
        return [], dict(base, status="取得不能", why=f"HTTP {r.status_code}")
    d = r.json()
    out = [{"result_type": "organic", "observed_order": i,
            "url": x.get("url"), "title": x.get("name")}
           for i, x in enumerate((d.get("webPages") or {}).get("value") or [],
                                 1)]
    return out, dict(base, status="取得", engine_note="Bing。Googleではない",
                     result_types_note="広告・動画・強調スニペットの区別は取れない",
                     organic_count=len(out))


def same_domain_duplicates(results):
    """同一ドメインの重複を**別に記録する。** 消さない。"""
    seen = {}
    for x in results:
        if x.get("result_type") != "organic":
            continue
        d = (x.get("url") or "").split("/")[2] if "//" in (x.get("url") or "") \
            else x.get("domain")
        if isinstance(d, list):
            d = d[0] if d else None
        seen.setdefault(d, []).append(x.get("observed_order"))
    return {k: v for k, v in seen.items() if k and len(v) > 1}

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


# 記事 → その記事が本文で扱っている案件だけ。**関係ない案件を取りに行かない**
ARTICLE_PROGRAMS = {
    "546": ["nativecamp"],
    "310": ["speek", "sptr"],
    "526": ["nativecamp_ryugaku", "phil_navi"],
}


def main(arg):
    import yaml
    src = sorted(x for x in SERP_DIR.glob("*.yaml") if "_full" not in x.name)
    if not src:
        print("SERPの控えが無い。先に検索結果を保存する")
        sys.exit(1)
    data = yaml.safe_load(src[-1].read_text(encoding="utf-8"))
    want = ([str(x) for x in data["articles"]] if arg in ("all", "")
            else [x.strip() for x in arg.split(",") if x.strip()])

    stamp = datetime.now(JST).strftime("%Y-%m-%d")
    full = {}
    for pid in want:
        rec = data["articles"].get(int(pid)) or data["articles"].get(pid)
        if not rec:
            print(f"[{pid}] 控えに無い。飛ばす")
            continue
        q = rec["query"]
        print(f"[{pid}] {q}")
        by_device = {}
        for dev in SERP_DEVICES:
            # **モバイルとデスクトップを分ける。** 混ぜて1つにしない
            results, meta = fetch_serp(q, dev)
            organic = [x for x in results if x["result_type"] == "organic"]
            by_device[dev] = {
                "meta": meta,
                "counts": {t: sum(1 for x in results
                                  if x["result_type"] == t)
                           for t in RESULT_TYPES},
                # **10件に満たなくても、そのまま。** 数合わせをしない
                "organic_count": len(organic),
                "padded_to_ten": False,
                "same_domain_duplicates": same_domain_duplicates(results),
                "results": results,
                # 本文の構造は、取れた自然検索だけを開いて取る
                "pages": scan_serp(pid, {"serp": organic}) if organic else [],
            }
            print(f"  {dev}: {meta['status']} / 自然検索 {len(organic)}件")
        full[pid] = {"query": q, "intent": rec.get("intent"),
                     "by_device": by_device}

    # 公式は、**その記事が本文で扱っている案件だけ**
    slugs = sorted({s for pid in want for s in ARTICLE_PROGRAMS.get(pid, [])})
    official = scan_official(slugs) if slugs else {}

    SERP_DIR.mkdir(parents=True, exist_ok=True)
    OFFICIAL_DIR.mkdir(parents=True, exist_ok=True)
    p1 = SERP_DIR / f"{stamp}_full.yaml"
    p1.write_text(yaml.safe_dump(
        {"fetched_at": now(),
         "order_field": "observed_order",
         "order_is_not_rank": "取得順であって掲載順位ではない",
         "conditions": {"locale": SERP_LOCALE, "country": SERP_COUNTRY,
                        "devices": SERP_DEVICES,
                        "result_types_separated": RESULT_TYPES},
         "rules": ["自然検索が10件未満でも、取れた件数のまま完了する",
                   "本文が取れないとき、検索スニペットで補完しない",
                   "同一ドメインの重複は消さず別に記録する"],
         "note": "他社の本文は保存していない。構造だけ",
         "articles": full}, allow_unicode=True, sort_keys=False, width=200),
        encoding="utf-8")
    p2 = OFFICIAL_DIR / f"{stamp}.yaml"
    p2.write_text(yaml.safe_dump(
        {"fetched_at": now(),
         "scope": "対象記事が本文で扱っている案件だけ",
         "rule": "取れなかった項目は None。**0として扱わない**",
         "programs": official}, allow_unicode=True, sort_keys=False,
        width=200), encoding="utf-8")
    print(f"\n→ {p1}\n→ {p2}")
    print("**記事もWordPressも触っていない。**")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "all")
