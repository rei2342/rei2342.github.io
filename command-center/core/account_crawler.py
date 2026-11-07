"""実アカウントの公開データを集め、文体を実測してペルソナを校正する。

取得経路（上から順に試す）:
  WordPress  … 公開 REST API (/wp-json/wp/v2/posts)
  note       … 公開 API (note.com/api/v2/creators/{id})
  X          … X API v2（X_BEARER_TOKEN）→ Playwright で公開ページ
  Threads    … Threads Graph API（THREADS_ACCESS_TOKEN）→ Playwright
  Instagram  … IG Graph API（IG_ACCESS_TOKEN + IG_USER_ID）→ Playwright
結果は data/calibration/<internal_key>.json に保存し、マスター（Astraの事実データ）は書き換えない。
ASP 管理画面・ログインが必要なページには入らない。
"""
from __future__ import annotations

import html
import os
import re
import statistics
from collections import Counter
from typing import Any
from urllib.parse import urlparse

import requests

from core import config as C
from core.account_loader import Account, get_account

UA = "Mozilla/5.0 (compatible; CommandCenterCrawler/1.0; own-account-calibration)"
TIMEOUT = 20
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
ENDINGS = ["です", "ます", "でした", "ました", "だ", "よ", "ね", "かも", "ない", "する", "した", "る", "た"]
FIRST_PERSON = ["私", "わたし", "僕", "ぼく", "俺", "うち", "自分", "あたし"]


def _get(url: str, **kw) -> requests.Response:
    h = {"User-Agent": UA, **kw.pop("headers", {})}
    return requests.get(url, headers=h, timeout=TIMEOUT, **kw)


def _strip(s: str) -> str:
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", s or "", flags=re.S)
    s = re.sub(r"<br\s*/?>|</p>", "\n", s)
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def handle_from_url(url: str) -> str | None:
    if not url:
        return None
    path = urlparse(url).path.strip("/")
    return path.split("/")[0].lstrip("@") or None


# ---------------------------------------------------------------- per platform
def crawl_wordpress(url: str, **_) -> dict:
    base = url.rstrip("/")
    r = _get(f"{base}/wp-json/wp/v2/posts", params={"per_page": 10, "_fields": "id,link,title,excerpt,date,content"})
    r.raise_for_status()
    posts = []
    for p in r.json():
        body = _strip(p.get("content", {}).get("rendered", ""))
        posts.append({"title": _strip(p.get("title", {}).get("rendered", "")), "url": p.get("link"),
                      "date": p.get("date"), "text": body[:1200]})
    site = {}
    try:
        s = _get(f"{base}/wp-json").json()
        site = {"name": s.get("name"), "description": s.get("description")}
    except Exception:
        pass
    return {"source": "wp_rest_api", "profile": site, "posts": posts}


def crawl_note(url: str, handle: str | None = None, **_) -> dict:
    h = handle or handle_from_url(url)
    prof = _get(f"https://note.com/api/v2/creators/{h}").json().get("data", {})
    cont = _get(f"https://note.com/api/v2/creators/{h}/contents", params={"kind": "note", "page": 1}).json()
    posts = []
    for n in (cont.get("data", {}) or {}).get("contents", [])[:15]:
        posts.append({"title": n.get("name"), "url": n.get("noteUrl") or f"https://note.com/{h}/n/{n.get('key')}",
                      "date": n.get("publishAt"), "text": (n.get("body") or n.get("description") or "")[:800],
                      "price": n.get("price"), "metrics": {"likes": n.get("likeCount")}})
    return {"source": "note_public_api",
            "profile": {"name": prof.get("nickname"), "bio": prof.get("profile"),
                        "followers": prof.get("followerCount"), "notes": prof.get("noteCount")},
            "posts": posts}


def crawl_x(url: str, handle: str | None = None, account_key: str = "", **_) -> dict:
    h = handle or handle_from_url(url)
    bearer = C.cred("X_BEARER_TOKEN", account_key)
    if bearer:
        hdr = {"Authorization": f"Bearer {bearer}"}
        u = _get(f"https://api.x.com/2/users/by/username/{h}", headers=hdr,
                 params={"user.fields": "description,public_metrics,name"})
        u.raise_for_status()
        user = u.json()["data"]
        t = _get(f"https://api.x.com/2/users/{user['id']}/tweets", headers=hdr,
                 params={"max_results": 20, "exclude": "retweets,replies", "tweet.fields": "created_at,public_metrics"})
        t.raise_for_status()
        posts = [{"text": x["text"], "url": f"https://x.com/{h}/status/{x['id']}", "date": x.get("created_at"),
                  "metrics": x.get("public_metrics")} for x in t.json().get("data", [])]
        return {"source": "x_api_v2", "profile": {"name": user.get("name"), "bio": user.get("description"),
                                                  "metrics": user.get("public_metrics")}, "posts": posts}
    d = crawl_with_browser(url, article_selector="article [data-testid='tweetText']")
    if d.get("partial"):
        d["error"] = "X は未ログインだと投稿を出さない。X_BEARER_TOKEN__<アカウント> を設定すると API v2 で投稿も取る（プロフィールは取得済み）"
    return d


def crawl_threads(url: str, account_key: str = "", **_) -> dict:
    tok = C.cred("THREADS_ACCESS_TOKEN", account_key)
    if tok:
        api = "https://graph.threads.net/v1.0"
        me = _get(f"{api}/me", params={"fields": "username,threads_biography", "access_token": tok}).json()
        th = _get(f"{api}/me/threads", params={"fields": "id,text,timestamp,permalink", "limit": 25,
                                               "access_token": tok}).json()
        posts = [{"text": x.get("text", ""), "url": x.get("permalink"), "date": x.get("timestamp")}
                 for x in th.get("data", []) if x.get("text")]
        return {"source": "threads_api", "profile": {"name": me.get("username"), "bio": me.get("threads_biography")},
                "posts": posts}
    return crawl_with_browser(url, article_selector="div[data-pressable-container]")


def crawl_instagram(url: str, account_key: str = "", **_) -> dict:
    tok, uid = C.cred("IG_ACCESS_TOKEN", account_key), C.cred("IG_USER_ID", account_key)
    if tok and uid:
        r = _get(f"https://graph.facebook.com/v21.0/{uid}",
                 params={"fields": "username,biography,followers_count,media.limit(20){caption,permalink,timestamp,"
                                   "media_type,like_count,comments_count}", "access_token": tok})
        r.raise_for_status()
        j = r.json()
        posts = [{"text": m.get("caption", ""), "url": m.get("permalink"), "date": m.get("timestamp"),
                  "metrics": {"likes": m.get("like_count"), "comments": m.get("comments_count")},
                  "media_type": m.get("media_type")} for m in j.get("media", {}).get("data", [])]
        return {"source": "ig_graph_api", "profile": {"name": j.get("username"), "bio": j.get("biography"),
                                                      "followers": j.get("followers_count")}, "posts": posts}
    return crawl_with_browser(url, article_selector="article h1, article span")


def crawl_with_browser(url: str, article_selector: str = "article") -> dict:
    """公開ページを Chromium で開いてプロフィールと見えている投稿テキストを拾う（ログインはしない）。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError("playwright 未インストール: pip install playwright && playwright install chromium") from e
    with sync_playwright() as pw:
        browser = C.launch_chromium(pw)
        page = browser.new_page(user_agent=UA.replace("CommandCenterCrawler/1.0; ", ""), locale="ja-JP")
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(4000)
        meta = page.evaluate("""() => {
            const g = n => (document.querySelector(`meta[property="${n}"],meta[name="${n}"]`)||{}).content||null;
            return {title: document.title, og_title: g('og:title'), description: g('og:description') || g('description')};
        }""")
        texts = page.eval_on_selector_all(article_selector, "els => els.map(e => e.innerText).filter(t => t && t.length > 15)")
        browser.close()
    seen, posts = set(), []
    for t in texts:
        lines = t.strip().split("\n")
        # Threads: 先頭の「ID / 日付」行と末尾の数字だけの行（いいね数等）を落とす
        while lines and (re.fullmatch(r"[A-Za-z0-9_.]{3,30}", lines[0].strip()) or re.fullmatch(r"[\d/年月日:\s時間分前週]+", lines[0].strip())):
            lines.pop(0)
        while lines and re.fullmatch(r"[\d,.万K\s]*", lines[-1].strip()):
            lines.pop()
        t = "\n".join(lines).strip()
        if len(t) < 15:
            continue
        if t not in seen:
            seen.add(t)
            posts.append({"text": t[:1000], "url": url})
    if meta.get("description") and re.search(r"アカウントを作成、またはアカウントにログイン|Log in|Sign up", meta["description"]):
        meta["description"] = None  # ログイン誘導の定型文はプロフィールではない
    out = {"source": "browser_public_page", "profile": {"name": meta.get("og_title") or meta.get("title"),
                                                          "bio": meta.get("description")}, "posts": posts[:20]}
    if not posts:  # プロフィールは残し、投稿が取れなかったことを明示する
        out["partial"] = True
        out["error"] = "公開ページに投稿が出ない（ログイン壁）。プロフィールのみ取得。API トークンを設定するとAPI経由で投稿も取る"
    return out


CRAWLERS = {"wordpress": crawl_wordpress, "note": crawl_note, "x": crawl_x,
            "threads": crawl_threads, "instagram": crawl_instagram}


# ---------------------------------------------------------------- style
def style_profile(texts: list[str]) -> dict[str, Any]:
    texts = [t for t in texts if t and len(t) >= 10]
    if not texts:
        return {}
    lens = [len(t) for t in texts]
    lines = [t.count("\n") + 1 for t in texts]
    sentences = [s for t in texts for s in re.split(r"[。！？!?\n]", t) if len(s.strip()) > 3]
    ends = Counter()
    for s in sentences:
        s = s.strip()
        for e in ENDINGS:
            if s.endswith(e):
                ends[e] += 1
                break
    fp = Counter({w: sum(t.count(w) for t in texts) for w in FIRST_PERSON})
    emoji = Counter(e for t in texts for e in EMOJI_RE.findall(t))
    return {
        "sample_count": len(texts),
        "avg_chars": round(statistics.mean(lens)),
        "median_chars": statistics.median(lens),
        "avg_lines": round(statistics.mean(lines), 1),
        "chars_per_line": round(sum(lens) / max(1, sum(lines)), 1),
        "kuten_rate": round(sum(t.count("。") for t in texts) / max(1, len(sentences)), 2),
        "desu_masu_ratio": round((ends["です"] + ends["ます"] + ends["でした"] + ends["ました"]) / max(1, sum(ends.values())), 2),
        "top_endings": ends.most_common(5),
        "first_person_counts": {k: v for k, v in fp.most_common() if v},
        "emoji_per_post": round(sum(emoji.values()) / len(texts), 2),
        "top_emoji": emoji.most_common(5),
        "question_rate": round(sum(t.count("？") + t.count("?") for t in texts) / len(texts), 2),
        "bracket_quote_rate": round(sum(t.count("「") for t in texts) / len(texts), 2),
    }


def summarize_tone(account: Account, data: dict, settings: dict) -> dict | None:
    if not any(os.environ.get(k) for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "REI_AFFSAKU")):
        return None
    from core.llm import generate_json

    samples = []
    for p, d in data.items():
        for post in (d.get("posts") or [])[:8]:
            samples.append(f"[{p}] {post.get('title') or ''}\n{post.get('text', '')[:500]}")
    schema = {
        "type": "object", "additionalProperties": False,
        "required": ["tone", "opening_patterns", "structure_patterns", "closing_patterns", "vocabulary", "avoid", "audience_signals"],
        "properties": {
            "tone": {"type": "string"},
            "opening_patterns": {"type": "array", "items": {"type": "string"}},
            "structure_patterns": {"type": "array", "items": {"type": "string"}},
            "closing_patterns": {"type": "array", "items": {"type": "string"}},
            "vocabulary": {"type": "array", "items": {"type": "string"}},
            "avoid": {"type": "array", "items": {"type": "string"}},
            "audience_signals": {"type": "array", "items": {"type": "string"}},
        },
    }
    system = ("あなたはSNS運用の文体アナリスト。与えられた実投稿だけを根拠に、書き出し・構成・締め・語彙の型を抽出する。"
              "投稿に無い経歴や実績を推測しない。文章はコピーせず、型として要約する。")
    user = f"アカウント: {account.label}\nAstraの調査メモ: {account.persona.get('tone_and_style')}\n\n実投稿:\n" + "\n---\n".join(samples[:30])
    return generate_json(system, user, schema, settings, max_tokens=8000)


# ---------------------------------------------------------------- entry
def crawl(account_key: str, urls: dict[str, str] | None = None, platforms: list[str] | None = None,
          use_llm: bool = True) -> dict:
    settings = C.load_settings()
    acct = get_account(account_key)
    targets = urls or {p: acct.platform(p)["url"] for p in acct.active_platforms()}
    if platforms:
        targets = {p: u for p, u in targets.items() if p in platforms}
    results: dict[str, Any] = {}
    for p, url in targets.items():
        fn = CRAWLERS.get(p)
        if not fn or not url:
            continue
        try:
            d = fn(url, handle=acct.handle(p) if not urls else handle_from_url(url), account_key=acct.key)
            d["ok"] = not d.get("partial")
        except Exception as e:  # 1媒体の失敗で全体を止めない
            d = {"ok": False, "error": f"{type(e).__name__}: {e}"[:400], "posts": []}
        d["url"] = url
        d["fetched_at"] = C.now_iso()
        results[p] = d
    texts = [x.get("text", "") for d in results.values() for x in d.get("posts", [])]
    bios = {p: (d.get("profile") or {}).get("bio") for p, d in results.items() if (d.get("profile") or {}).get("bio")}
    calib = {
        "account_key": acct.key,
        "label": acct.label,
        "fetched_at": C.now_iso(),
        "platforms": results,
        "style_metrics": style_profile(texts),
        "style_by_platform": {p: style_profile([x.get("text", "") for x in d.get("posts", [])]) for p, d in results.items()},
        "profiles": bios,
        "recent_titles": [x.get("title") for d in results.values() for x in d.get("posts", []) if x.get("title")][:30],
        "existing_urls": [x.get("url") for d in results.values() for x in d.get("posts", []) if x.get("url")][:60],
    }
    if use_llm and texts:
        try:
            calib["tone_summary"] = summarize_tone(acct, results, settings)
        except Exception as e:
            calib["tone_summary_error"] = str(e)[:300]
    prev = acct.calibration()
    C.write_json(C.DATA_DIR / "calibration" / f"{acct.key}.json", calib)
    if prev:
        C.append_jsonl(C.DATA_DIR / "calibration" / "history.jsonl",
                       {"at": C.now_iso(), "account": acct.key, "prev_fetched_at": prev.get("fetched_at")})
    return calib
