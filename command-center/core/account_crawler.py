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
import json
import os
import re
import statistics
from collections import Counter
from typing import Any
from pathlib import Path
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
    return _login_wall_chain("x", url, h, account_key, article_selector="article [data-testid='tweetText']",
                             extra=[lambda: crawl_nitter_rss(h)],
                             hint="X は未ログインだと投稿を出さない。X_BEARER_TOKEN__<アカウント> を入れるか、"
                                  "python main.py browser-login x で専用プロファイルにログインする")


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


def crawl_instagram(url: str, handle: str | None = None, account_key: str = "", **_) -> dict:
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
    return _login_wall_chain("instagram", url, handle or handle_from_url(url), account_key, article_selector="article h1, article span",
                             ig=True, hint="公開ページに投稿が出ない（ログイン壁）。IG_ACCESS_TOKEN を入れるか、"
                                           "python main.py browser-login instagram で専用プロファイルにログインする")


# ---------------------------------------------------------------- ログイン壁の回避（X / IG）
def profile_dir(platform: str) -> Path:
    """Playwright の persistent context 用の専用プロファイル。人が一度だけ手でログインする（パスワードは保存しない）。"""
    base = C.load_settings().get("crawl", {}).get("browser_profile_dir", "data/browser_profiles")
    return C.ROOT / base / platform


def has_profile(platform: str) -> bool:
    d = profile_dir(platform)
    return d.exists() and any(d.iterdir())


def _login_wall_chain(platform: str, url: str, handle: str | None, account_key: str, article_selector: str,
                      hint: str, extra: list | None = None, ig: bool = False) -> dict:
    """API が無いときの取得順: ログイン済み専用プロファイル → ローカルの投稿ログ → (X) Nitter RSS → 公開ページ。
    取れた経路を source に、試した経路を tried に残す。複数経路の投稿は重複を除いて合わせる。"""
    tried, got, profile = [], [], {}
    steps = []
    if has_profile(platform):
        steps.append(("browser_profile", lambda: crawl_with_browser(url, article_selector, persistent=platform, ig=ig)))
    steps.append(("local_logs", lambda: crawl_local_logs(platform, handle, account_key)))
    steps += [("nitter_rss", f) for f in (extra or [])]
    steps.append(("browser_public_page", lambda: crawl_with_browser(url, article_selector, ig=ig)))
    for name, fn in steps:
        try:
            d = fn() or {}
        except Exception as e:
            tried.append(f"{name}: {type(e).__name__}: {str(e)[:120]}")
            continue
        n = len(d.get("posts") or [])
        tried.append(f"{name}: {n}件")
        if not profile.get("bio") and (d.get("profile") or {}).get("bio"):
            profile = d["profile"]
        elif not profile and d.get("profile"):
            profile = d["profile"]
        if n:
            got.append((d.get("source") or name, d["posts"]))
            if name == "browser_profile":
                break  # ログイン済みで直近が取れたら十分
    seen, posts = set(), []
    for _, ps in got:
        for x in ps:
            key = (x.get("text") or "")[:80]
            if key and key not in seen:
                seen.add(key)
                posts.append(x)
    posts.sort(key=lambda x: x.get("date") or "", reverse=True)
    out = {"source": "+".join(dict.fromkeys(s for s, _ in got)) or "browser_public_page", "profile": profile,
           "posts": posts[:25], "tried": tried}
    if not posts:
        out["partial"] = True
        out["error"] = hint
    return out


def _local_log_paths(platform: str, handle: str | None, account_key: str) -> list:
    """data/local_posts/<internal_key>/<platform>.jsonl（取り込み済みログ）＋ settings.crawl.local_log_globs。"""
    import glob

    paths = [(C.DATA_DIR / "local_posts" / account_key / f"{platform}.jsonl", True)]
    for ent in (C.load_settings().get("crawl", {}).get("local_log_globs") or []):
        # 文字列 = 本人の投稿を url/handle で絞る。{path, account} = そのアカウント専用のログ（絞らない）
        pat, owner = (ent, None) if isinstance(ent, str) else (ent.get("path", ""), ent.get("account"))
        if owner and owner != account_key:
            continue
        pat = pat.replace("{platform}", platform).replace("{handle}", handle or "").replace("{account}", account_key)
        pp = Path(pat).expanduser()
        pp = pp if pp.is_absolute() else C.ROOT / pp  # 相対パスは command-center/ 基準
        paths += [(Path(p), bool(owner)) for p in glob.glob(str(pp), recursive=True)]
    return [(p, own) for p, own in dict.fromkeys(paths) if p.exists()]


def crawl_local_logs(platform: str, handle: str | None, account_key: str) -> dict:
    """運用ログ（jsonl / json 配列）から、そのアカウント・媒体の投稿本文を読む。
    1行1投稿で text|caption|body|full_text のどれかを持つものを拾い、url/handle/account で本人の投稿に絞る。"""
    posts = []
    hl = (handle or "").lower()
    for p, own_file in _local_log_paths(platform, handle, account_key):
        raw = p.read_text(encoding="utf-8", errors="ignore")
        try:
            rows = json.loads(raw)
            if isinstance(rows, dict):
                rows = rows.get("posts") or rows.get("data") or [rows]
        except json.JSONDecodeError:
            rows = []
            for line in raw.splitlines():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        for r in rows:
            if not isinstance(r, dict):
                continue
            text = r.get("text") or r.get("caption") or r.get("full_text") or r.get("body") or ""
            if len(text.strip()) < 10:
                continue
            u = r.get("url") or r.get("permalink") or r.get("posted_url") or ""
            who = str(r.get("handle") or r.get("username") or r.get("account") or "").lstrip("@").lower()
            if not own_file and hl and hl not in u.lower() and who != hl:
                continue  # 他人の投稿（競合調査ログなど）は混ぜない
            posts.append({"text": text[:1000], "url": u or None, "date": r.get("date") or r.get("posted_at") or r.get("timestamp"),
                          "metrics": r.get("metrics"), "log_file": str(p)})
    return {"source": "local_logs", "profile": {}, "posts": posts}


def crawl_nitter_rss(handle: str | None) -> dict:
    """Nitter 系ミラーの RSS（settings.crawl.nitter_instances）。多くは止まっているので短いタイムアウトで順に試す。"""
    import xml.etree.ElementTree as ET

    if not handle:
        return {}
    last = None
    for inst in C.load_settings().get("crawl", {}).get("nitter_instances") or []:
        try:
            r = requests.get(f"{inst.rstrip('/')}/{handle}/rss", headers={"User-Agent": UA}, timeout=8)
            if r.status_code != 200 or "<rss" not in r.text[:500]:
                last = f"{inst}: HTTP {r.status_code}"
                continue
            root = ET.fromstring(r.content)
            posts = []
            for it in root.iter("item"):
                text = _strip(it.findtext("description") or it.findtext("title") or "")
                if len(text) >= 10 and not text.startswith("RT by"):
                    posts.append({"text": text[:1000], "url": (it.findtext("link") or "").replace(inst.rstrip("/"), "https://x.com"),
                                  "date": it.findtext("pubDate")})
            if posts:
                return {"source": f"nitter_rss({inst})", "profile": {}, "posts": posts[:20]}
        except Exception as e:
            last = f"{inst}: {type(e).__name__}"
    raise RuntimeError(last or "nitter_instances 未設定")


def crawl_with_browser(url: str, article_selector: str = "article", persistent: str | None = None,
                       ig: bool = False) -> dict:
    """Chromium でページを開いてプロフィールと見えている投稿テキストを拾う。
    persistent=媒体名 のときは専用プロファイル（人が手でログイン済み）を使う。ここでログイン操作はしない。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError("playwright 未インストール: pip install playwright && playwright install chromium") from e
    js_meta = """() => {
            const g = n => (document.querySelector(`meta[property="${n}"],meta[name="${n}"]`)||{}).content||null;
            return {title: document.title, og_title: g('og:title'), description: g('og:description') || g('description')};
        }"""
    with sync_playwright() as pw:
        if persistent:
            ctx = pw.chromium.launch_persistent_context(str(profile_dir(persistent)), headless=True, locale="ja-JP")
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
        else:
            browser = C.launch_chromium(pw)
            page = browser.new_page(user_agent=UA.replace("CommandCenterCrawler/1.0; ", ""), locale="ja-JP")
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(4000)
        meta = page.evaluate(js_meta)
        if persistent:
            for _ in range(3):  # 直近をもう少し読み込む
                page.mouse.wheel(0, 2500)
                page.wait_for_timeout(1500)
        texts = page.eval_on_selector_all(article_selector, "els => els.map(e => e.innerText).filter(t => t && t.length > 15)")
        if persistent and ig:
            # IG はグリッドから投稿URLを拾い、各投稿のキャプションを読む
            links = page.eval_on_selector_all("a[href*='/p/'], a[href*='/reel/']", "els => [...new Set(els.map(e => e.href))]")[:12]
            texts = []
            for ln in links:
                page.goto(ln, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(2500)
                cap = page.evaluate(js_meta).get("description") or ""
                cap = re.sub(r'^.*?: "|"\s*$', "", cap, flags=re.S) if ': "' in cap else cap
                if len(cap) > 15:
                    texts.append(cap)
        (ctx if persistent else browser).close()
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
    out = {"source": "browser_profile" if persistent else "browser_public_page", "profile": {"name": meta.get("og_title") or meta.get("title"),
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
    from core import llm

    if not llm.available():
        return None
    generate_json = llm.generate_json

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
