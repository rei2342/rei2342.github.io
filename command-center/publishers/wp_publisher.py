"""WordPress REST API への投稿（アプリケーションパスワード認証）。"""
from __future__ import annotations

import requests

from core import config as C
from publishers.base import outbox


def endpoint(acct) -> str:
    wp = acct.platform("wordpress")
    return (wp.get("rest_api_endpoint") or wp["url"].rstrip("/") + "/wp-json/wp/v2").rstrip("/")


def publish(acct, platform, body, draft, settings, dry_run=True) -> dict:
    status = settings.get("publishing", {}).get("wordpress", {}).get("default_status", "draft")
    payload = {"title": body["title"], "content": body["html"], "excerpt": body.get("excerpt", ""),
               "slug": body.get("slug") or None, "status": status}
    url = f"{endpoint(acct)}/posts"
    if dry_run:
        return {"ok": True, "dry_run": True, "outbox": outbox("wordpress", acct.key, {"url": url, "payload": payload})}
    auth = (C.cred("WP_USER", acct.key, settings), C.cred("WP_APP_PASSWORD", acct.key, settings))
    r = requests.post(url, json={k: v for k, v in payload.items() if v is not None}, auth=auth, timeout=60)
    if r.status_code >= 300:
        return {"ok": False, "status_code": r.status_code, "error": r.text[:400]}
    j = r.json()
    return {"ok": True, "post_id": j.get("id"), "url": j.get("link"), "status": j.get("status")}


def recent_posts(acct, n: int = 20) -> list[dict]:
    r = requests.get(f"{endpoint(acct)}/posts", params={"per_page": n, "_fields": "id,link,title,date"}, timeout=30)
    r.raise_for_status()
    return [{"id": p["id"], "url": p["link"], "title": p["title"]["rendered"], "date": p["date"]} for p in r.json()]


def upload_media(acct, path: str, settings, title: str | None = None) -> dict:
    """/wp-json/wp/v2/media に画像を上げて公開URL（source_url）を返す。"""
    import mimetypes
    from pathlib import Path

    p = Path(path)
    ctype = mimetypes.guess_type(p.name)[0] or "image/png"
    auth = (C.cred("WP_USER", acct.key, settings), C.cred("WP_APP_PASSWORD", acct.key, settings))
    r = requests.post(f"{endpoint(acct)}/media", data=p.read_bytes(), auth=auth, timeout=120,
                      headers={"Content-Type": ctype, "Content-Disposition": f'attachment; filename="{p.name}"'})
    if r.status_code >= 300:
        raise RuntimeError(f"WP media upload {r.status_code}: {r.text[:300]}")
    j = r.json()
    if title:
        requests.post(f"{endpoint(acct)}/media/{j['id']}", json={"title": title, "alt_text": title}, auth=auth, timeout=30)
    return {"id": j["id"], "url": j["source_url"]}
