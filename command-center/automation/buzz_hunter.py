"""稼働中の X / Threads を監視し、伸び始めた投稿のリプライ欄に誘導リンクをぶら下げる。

- 監視対象 = マスターで active ＋ 認証情報がある X / Threads（アカウント名は持たない）
- 判定 = 総インプレッション or 1時間あたりの伸び or エンゲージ率（settings.buzz.thresholds）
- リプライ本文 = その投稿を配信した下書きの buzz_followup → 無ければ自分の note/WP への誘導テンプレ
- アフィリンク = allow_affiliate_in_auto_reply が true かつ、その媒体URLが登録媒体と一致し、
                 auto_publish_allowed（または overrides）の案件だけ。既定は自分の記事URLのみ。
- 1投稿1回・1アカウント1日上限・深夜帯停止・dry_run 中は送らない
"""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone

from core import config as C
from core import drafts, guards
from core.account_loader import Account, affiliate_pool, get_accounts, get_account

ALERTS = C.DATA_DIR / "buzz" / "alerts.json"


def _alerts() -> dict:
    return C.read_json(ALERTS, {}) or {}


def _save(a: dict) -> None:
    C.write_json(ALERTS, a)


def _metrics(acct: Account, platform: str, settings: dict, hours: int) -> list[dict]:
    if platform == "x":
        from publishers.x_publisher import recent_metrics

        return recent_metrics(acct, settings, hours)
    if platform == "threads":
        from publishers.meta_publisher import threads_recent_metrics

        return threads_recent_metrics(acct, settings, hours)
    return []


def evaluate(post: dict, platform: str, th: dict, min_age_min: int) -> tuple[bool, dict]:
    created = datetime.fromisoformat(post["created_at"])
    age_h = max((datetime.now(timezone.utc) - created).total_seconds() / 3600, 1 / 60)
    views = post.get("impressions") if platform == "x" else post.get("views")
    views = views or 0
    rate = views / age_h
    er = (post.get("engagements", 0) / views) if views else 0
    sig = {"views": views, "age_hours": round(age_h, 2), "views_per_hour": round(rate), "engagement_rate": round(er, 4)}
    if age_h * 60 < min_age_min:
        return False, sig
    if platform == "x":
        hit = views >= th.get("impressions", 1e12) or rate >= th.get("impressions_per_hour", 1e12) or \
            (views >= 500 and er >= th.get("engagement_rate", 1))
    else:
        hit = views >= th.get("views", 1e12) or rate >= th.get("views_per_hour", 1e12)
    return hit, sig


def build_followup(acct: Account, platform: str, post: dict, settings: dict) -> tuple[str, list[dict]]:
    pr = settings.get("affiliate", {}).get("pr_label", "PR")
    led = [e for e in drafts.ledger() if e.get("platform") == platform and
           (e.get("post_id") == post["post_id"] or post["post_id"] in (e.get("post_ids") or []))]
    _, aff_urls = _reply_allowlist(acct, platform, settings)
    text = None
    if led and led[-1].get("followup"):
        text = led[-1]["followup"]
    if not text:
        dest = next((d for d in acct.own_destinations() if d["type"] in ("wordpress", "note", "note_product")), None) \
            or next(iter(acct.own_destinations()), None)
        if not dest:
            return "", [{"level": "error", "msg": "誘導先（note/WP/LINE）がマスターに無い"}]
        text = f"この話の続き・確認の手順はこちらにまとめています\n{dest['url']}"
    if any(u in text for u in aff_urls) and pr not in text:
        text = f"{pr} {text}"
    return text, check_reply(acct, platform, text, settings)


def _reply_allowlist(acct: Account, platform: str, settings: dict) -> tuple[list[str], list[str]]:
    allowed = [d["url"] for d in acct.own_destinations()]
    aff: list[str] = []
    if settings.get("buzz", {}).get("allow_affiliate_in_auto_reply"):
        pool = affiliate_pool(acct, acct.platform(platform).get("url"), settings, for_auto_publish=True)
        aff = [a["affiliate_url"] for a in pool if a["usable"]]
    return allowed + aff, aff


def check_reply(acct: Account, platform: str, text: str, settings: dict) -> list[dict]:
    allowed, aff = _reply_allowlist(acct, platform, settings)
    return guards.check_platform(platform, {"posts": [text]},
                                 {"allowed_urls": allowed, "affiliate_urls": aff,
                                  "pr_label": settings.get("affiliate", {}).get("pr_label", "PR")},
                                 settings.get("platform_limits", {}))


def scan(settings: dict | None = None) -> list[dict]:
    s = settings or C.load_settings()
    b = s.get("buzz", {})
    alerts = _alerts()
    new = []
    for acct in get_accounts():
        for p in b.get("platforms", ["x", "threads"]):
            if not acct.is_active(p) or not C.has_creds(p, acct.key, s):
                continue
            try:
                posts = _metrics(acct, p, s, int(b.get("lookback_hours", 48)))
            except Exception as e:
                C.append_jsonl(C.DATA_DIR / "buzz" / "errors.jsonl", {"at": C.now_iso(), "account": acct.key, "platform": p, "error": str(e)[:300]})
                continue
            C.append_jsonl(C.DATA_DIR / "buzz" / "metrics.jsonl",
                           {"at": C.now_iso(), "account": acct.key, "platform": p,
                            "posts": [{k: x.get(k) for k in ("post_id", "impressions", "views", "engagements", "created_at")} for x in posts]})
            for post in posts:
                hit, sig = evaluate(post, p, (b.get("thresholds") or {}).get(p, {}), int(b.get("min_age_minutes", 30)))
                aid = hashlib.md5(f"{acct.key}:{p}:{post['post_id']}".encode()).hexdigest()[:12]
                if aid in alerts:
                    alerts[aid]["signal"] = sig
                    continue
                if not hit:
                    continue
                text, issues = build_followup(acct, p, post, s)
                alerts[aid] = {"id": aid, "account_key": acct.key, "account_label": acct.label, "platform": p,
                               "post_id": post["post_id"], "post_url": post.get("url"), "post_text": post.get("text", "")[:280],
                               "signal": sig, "detected_at": C.now_iso(), "status": "new",
                               "reply_text": text, "issues": issues}
                new.append(alerts[aid])
    _save(alerts)
    return new


def _quiet(settings) -> bool:
    q = settings.get("schedule", {}).get("quiet_hours_jst") or []
    if len(q) != 2:
        return False
    h = datetime.now(C.JST).hour
    a, z = q
    return a <= h < z if a < z else (h >= a or h < z)


def replied_today(account_key: str) -> int:
    today = datetime.now(C.JST).date().isoformat()
    return sum(1 for a in _alerts().values() if a["account_key"] == account_key and a.get("status") == "replied"
               and str(a.get("replied_at_jst", "")).startswith(today))


def execute(alert_id: str, live: bool = False, text: str | None = None, force: bool = False) -> dict:
    s = C.load_settings()
    alerts = _alerts()
    a = alerts.get(alert_id)
    if not a:
        raise KeyError(alert_id)
    if a["status"] == "replied":
        return {"ok": False, "skipped": "リプライ済み"}
    if text:
        a["reply_text"] = text
        a["issues"] = check_reply(get_account(a["account_key"]), a["platform"], text, s)
    if guards.has_errors(a.get("issues", [])):
        return {"ok": False, "skipped": "検査 error: " + "; ".join(i["msg"] for i in a["issues"] if i["level"] == "error")}
    if not force:
        if _quiet(s):
            return {"ok": False, "skipped": "深夜帯（quiet_hours_jst）"}
        if replied_today(a["account_key"]) >= int(s.get("buzz", {}).get("max_replies_per_account_per_day", 3)):
            return {"ok": False, "skipped": "本日の上限"}
    dry = (not live) or C.is_dry_run(s)
    acct = get_account(a["account_key"])
    if a["platform"] == "x":
        from publishers.x_publisher import reply
    else:
        from publishers.meta_publisher import reply
    res = reply(acct, a["post_id"], a["reply_text"], s, dry_run=dry)
    if res.get("ok") and not dry:
        a["status"] = "replied"
        a["replied_at"] = C.now_iso()
        a["replied_at_jst"] = datetime.now(C.JST).isoformat()
        a["reply_result"] = res
    else:
        a["last_attempt"] = {"at": C.now_iso(), "dry_run": dry, "result": res}
    alerts[alert_id] = a
    _save(alerts)
    return {"dry_run": dry, **res}


def dismiss(alert_id: str) -> None:
    al = _alerts()
    if alert_id in al:
        al[alert_id]["status"] = "dismissed"
        _save(al)


def run_once(live: bool = False) -> dict:
    s = C.load_settings()
    new = scan(s)
    done = []
    if s.get("buzz", {}).get("auto_reply") and live:
        for a in new:
            done.append({"alert": a["id"], **execute(a["id"], live=True)})
    return {"new_alerts": new, "auto_replies": done}


def loop(live: bool = False) -> None:
    s = C.load_settings()
    iv = int(s.get("schedule", {}).get("buzz_hunter_interval_minutes", 30)) * 60
    while True:
        r = run_once(live)
        print(f"[{C.now_iso()}] new={len(r['new_alerts'])} replied={len(r['auto_replies'])}", flush=True)
        time.sleep(iv)
