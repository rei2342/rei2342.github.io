"""X API v2（OAuth1.0a ユーザーコンテキスト）でスレッド投稿・リプライ・指標取得。

Playwright での自動投稿は X の規約（自動化ルール）に抵触するので実装しない。API だけを使う。
"""
from __future__ import annotations

from datetime import datetime, timezone

from core import config as C
from publishers.base import outbox


def client(acct, settings):
    import tweepy

    return tweepy.Client(
        consumer_key=C.cred("X_API_KEY", acct.key, settings),
        consumer_secret=C.cred("X_API_SECRET", acct.key, settings),
        access_token=C.cred("X_ACCESS_TOKEN", acct.key, settings),
        access_token_secret=C.cred("X_ACCESS_TOKEN_SECRET", acct.key, settings),
    )


def publish(acct, platform, body, draft, settings, dry_run=True) -> dict:
    posts = body["posts"]
    if dry_run:
        return {"ok": True, "dry_run": True, "outbox": outbox("x", acct.key, {"thread": posts})}
    c = client(acct, settings)
    ids, prev = [], None
    for text in posts:
        r = c.create_tweet(text=text, in_reply_to_tweet_id=prev, user_auth=True)
        prev = r.data["id"]
        ids.append(prev)
    h = acct.handle("x")
    return {"ok": True, "post_id": ids[0], "post_ids": ids, "url": f"https://x.com/{h}/status/{ids[0]}"}


def reply(acct, post_id: str, text: str, settings, dry_run=True) -> dict:
    if dry_run:
        return {"ok": True, "dry_run": True, "outbox": outbox("x", acct.key, {"reply_to": post_id, "text": text})}
    r = client(acct, settings).create_tweet(text=text, in_reply_to_tweet_id=post_id, user_auth=True)
    return {"ok": True, "post_id": r.data["id"]}


def recent_metrics(acct, settings, hours: int = 48) -> list[dict]:
    """自分の直近投稿。non_public_metrics（impression_count）は本人のユーザーコンテキストで取れる。"""
    c = client(acct, settings)
    me = c.get_me(user_auth=True).data
    since = datetime.now(timezone.utc).timestamp() - hours * 3600
    r = c.get_users_tweets(me.id, max_results=50, exclude=["retweets", "replies"], user_auth=True,
                           tweet_fields=["created_at", "public_metrics", "non_public_metrics", "conversation_id"])
    out = []
    for t in r.data or []:
        if t.created_at.timestamp() < since:
            continue
        pm, npm = t.public_metrics or {}, t.non_public_metrics or {}
        imp = npm.get("impression_count") or pm.get("impression_count") or 0
        eng = sum(pm.get(k, 0) for k in ("like_count", "retweet_count", "reply_count", "quote_count", "bookmark_count"))
        out.append({"post_id": str(t.id), "text": t.text, "created_at": t.created_at.isoformat(),
                    "impressions": imp, "engagements": eng, "metrics": {**pm, **npm},
                    "url": f"https://x.com/{acct.handle('x')}/status/{t.id}"})
    return out
