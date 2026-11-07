"""Threads API / Instagram Graph API。

Threads: POST /{user}/threads (TEXT, reply_to_id) → /{user}/threads_publish
Instagram: 画像コンテナ(is_carousel_item) ×N → CAROUSEL コンテナ → /media_publish
IG は画像を公開URLで渡す必要がある（settings.publishing.instagram.public_media_base_url）。
"""
from __future__ import annotations

import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from core import config as C
from publishers.base import outbox

THREADS = "https://graph.threads.net/v1.0"
GRAPH = "https://graph.facebook.com/v21.0"


def _ok(r: requests.Response) -> dict:
    if r.status_code >= 300:
        raise RuntimeError(f"{r.status_code}: {r.text[:300]}")
    return r.json()


# ---------------------------------------------------------------- Threads
def _t_token(acct, s):
    return C.cred("THREADS_ACCESS_TOKEN", acct.key, s), C.cred("THREADS_USER_ID", acct.key, s) or "me"


def threads_post(acct, text: str, settings, reply_to: str | None = None) -> str:
    tok, uid = _t_token(acct, settings)
    data = {"media_type": "TEXT", "text": text, "access_token": tok}
    if reply_to:
        data["reply_to_id"] = reply_to
    cid = _ok(requests.post(f"{THREADS}/{uid}/threads", data=data, timeout=30))["id"]
    time.sleep(2)  # コンテナ処理待ち（公式推奨は最大30秒）
    for _ in range(10):
        r = requests.post(f"{THREADS}/{uid}/threads_publish", data={"creation_id": cid, "access_token": tok}, timeout=30)
        if r.status_code < 300:
            return r.json()["id"]
        time.sleep(3)
    raise RuntimeError(f"threads_publish 失敗: {r.text[:300]}")


def threads_recent_metrics(acct, settings, hours: int = 48) -> list[dict]:
    tok, uid = _t_token(acct, settings)
    j = _ok(requests.get(f"{THREADS}/{uid}/threads", params={"fields": "id,text,timestamp,permalink",
                                                             "limit": 25, "access_token": tok}, timeout=30))
    since = datetime.now(timezone.utc).timestamp() - hours * 3600
    out = []
    for t in j.get("data", []):
        ts = datetime.fromisoformat(t["timestamp"].replace("+0000", "+00:00"))
        if ts.timestamp() < since:
            continue
        ins = requests.get(f"{THREADS}/{t['id']}/insights", params={"metric": "views,likes,replies,reposts,quotes",
                                                                     "access_token": tok}, timeout=30)
        m = {}
        if ins.status_code < 300:
            for d in ins.json().get("data", []):
                vals = d.get("values") or [{}]
                m[d["name"]] = vals[0].get("value", d.get("total_value", {}).get("value", 0))
        out.append({"post_id": t["id"], "text": t.get("text", ""), "created_at": ts.isoformat(), "url": t.get("permalink"),
                    "views": m.get("views", 0), "engagements": sum(m.get(k, 0) for k in ("likes", "replies", "reposts", "quotes")),
                    "metrics": m})
    return out


# ---------------------------------------------------------------- Instagram
def media_host_account(acct, settings):
    """IG 画像を置く WP アカウント: 自分の WP → settings の media_wp_account → global_fallback_account。"""
    from core.account_loader import get_account

    if acct.is_active("wordpress") and C.has_creds("wordpress", acct.key, settings):
        return acct
    ig = settings.get("publishing", {}).get("instagram", {})
    key = ig.get("media_wp_account") or settings.get("credentials", {}).get("global_fallback_account")
    if key:
        host = get_account(key)
        if host.is_active("wordpress") and C.has_creds("wordpress", host.key, settings):
            return host
    return None


def _public_urls(paths: list[str], draft: dict, acct, settings) -> list[str]:
    ig = settings.get("publishing", {}).get("instagram", {})
    base = (ig.get("public_media_base_url") or "").rstrip("/")
    if base:  # 静的ホスティングを明示している場合
        media_root = C.ROOT / ig.get("media_dir", "data/media")
        urls = []
        for p in paths:
            p = Path(p)
            dest = media_root / draft["id"] / p.name
            if p.resolve() != dest.resolve():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest)
            urls.append(f"{base}/{draft['id']}/{p.name}")
        return urls
    host = media_host_account(acct, settings)
    if not host:
        raise RuntimeError("IG 画像の置き場が無い: 認証済みの WordPress が無く public_media_base_url も未設定")
    from publishers.wp_publisher import upload_media

    cache = draft.setdefault("results", {}).setdefault("instagram_media", {})
    urls = []
    for p in paths:
        if p not in cache:  # 再試行時に二重アップロードしない
            cache[p] = upload_media(host, p, settings, title=f"{acct.label} {Path(p).stem}")
            from core import drafts as D

            D.save(draft)
        urls.append(cache[p]["url"])
    return urls


def ig_carousel(acct, body, draft, settings) -> dict:
    tok, uid = C.cred("IG_ACCESS_TOKEN", acct.key, settings), C.cred("IG_USER_ID", acct.key, settings)
    urls = _public_urls(body.get("image_paths", []), draft, acct, settings)
    children = []
    for u in urls:
        children.append(_ok(requests.post(f"{GRAPH}/{uid}/media", data={"image_url": u, "is_carousel_item": "true",
                                                                          "access_token": tok}, timeout=60))["id"])
    caption = body["caption"]
    tags = " ".join(t if t.startswith("#") else "#" + t for t in body.get("hashtags", []))
    if tags and tags not in caption:
        caption = f"{caption}\n\n{tags}"
    cid = _ok(requests.post(f"{GRAPH}/{uid}/media", data={"media_type": "CAROUSEL", "children": ",".join(children),
                                                           "caption": caption, "access_token": tok}, timeout=60))["id"]
    for _ in range(20):
        st = _ok(requests.get(f"{GRAPH}/{cid}", params={"fields": "status_code", "access_token": tok}, timeout=30))
        if st.get("status_code") == "FINISHED":
            break
        time.sleep(3)
    mid = _ok(requests.post(f"{GRAPH}/{uid}/media_publish", data={"creation_id": cid, "access_token": tok}, timeout=60))["id"]
    link = _ok(requests.get(f"{GRAPH}/{mid}", params={"fields": "permalink", "access_token": tok}, timeout=30)).get("permalink")
    return {"ok": True, "post_id": mid, "url": link}


# ---------------------------------------------------------------- entry
def publish(acct, platform, body, draft, settings, dry_run=True) -> dict:
    if platform == "threads":
        if dry_run:
            return {"ok": True, "dry_run": True, "outbox": outbox("threads", acct.key, {"tree": body["posts"]})}
        ids, prev = [], None
        for text in body["posts"]:
            prev = threads_post(acct, text, settings, reply_to=prev)
            ids.append(prev)
        return {"ok": True, "post_id": ids[0], "post_ids": ids, "url": f"https://www.threads.com/@{acct.handle('threads')}"}
    if platform == "instagram":
        if dry_run:
            host = media_host_account(acct, settings)
            return {"ok": True, "dry_run": True, "outbox": outbox("instagram", acct.key, {
                "images": body.get("image_paths", []), "caption": body["caption"], "hashtags": body.get("hashtags", []),
                "media_host": (f"{host.label} WP /wp-json/wp/v2/media" if host else
                               settings.get("publishing", {}).get("instagram", {}).get("public_media_base_url") or "未確定")})}
        return ig_carousel(acct, body, draft, settings)
    raise ValueError(platform)


def reply(acct, post_id: str, text: str, settings, dry_run=True) -> dict:
    if dry_run:
        return {"ok": True, "dry_run": True, "outbox": outbox("threads", acct.key, {"reply_to": post_id, "text": text})}
    return {"ok": True, "post_id": threads_post(acct, text, settings, reply_to=post_id)}
