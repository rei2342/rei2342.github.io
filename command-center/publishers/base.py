"""配信の共通ゲート。承認済み・書き込み許可・認証情報・dry_run を全部ここで見る。"""
from __future__ import annotations

from typing import Any

from core import config as C
from core import drafts
from core.account_loader import get_account


class PublishBlocked(RuntimeError):
    pass


def outbox(platform: str, account_key: str, payload: dict) -> str:
    p = C.data_path("outbox", platform, f"{account_key}-{C.now_iso().replace(':', '')}.json")
    C.write_json(p, payload)
    return str(p)


def _module(platform: str):
    from publishers import meta_publisher, note_publisher, wp_publisher, x_publisher

    return {"wordpress": wp_publisher, "note": note_publisher, "x": x_publisher,
            "threads": meta_publisher, "instagram": meta_publisher}[platform]


def check_gate(draft: dict, platform: str, settings: dict) -> tuple[bool, str]:
    acct = get_account(draft["account_key"])
    route = {r.platform: r for r in acct.route(settings)}.get(platform)
    if not route or not route.readable:
        return False, f"{platform} は稼働媒体ではない"
    st = draft.get("platform_status", {}).get(platform)
    if st == "published":
        return False, "配信済み"
    if settings.get("publishing", {}).get("require_approval", True) and st != "approved":
        return False, "未承認（approve してから配信）"
    if any(i["level"] == "error" and i["platform"] == platform for i in draft.get("issues", [])):
        return False, "検査 error が残っている"
    if not route.write_enabled:
        return False, "settings.yaml publishing.enabled で未許可"
    if not route.has_credentials:
        return False, "認証情報が未設定"
    return True, "OK"


def publish_draft(draft_id: str, platforms: list[str] | None = None, live: bool = False) -> dict[str, Any]:
    """live=False（既定）または settings の dry_run=true なら外部に送らず outbox に保存。"""
    settings = C.load_settings()
    dry = (not live) or C.is_dry_run(settings)
    d = drafts.get(draft_id)
    acct = get_account(d["account_key"])
    results = {}
    for p in platforms or list(d["outputs"].keys()):
        ok, why = check_gate(d, p, settings)
        if not ok and not dry:
            results[p] = {"ok": False, "skipped": why}
            continue
        try:
            res = _module(p).publish(acct, p, d["outputs"][p], d, settings, dry_run=dry)
            res.setdefault("gate", why)
            results[p] = res
            if res.get("ok") and not dry:
                drafts.mark(draft_id, p, "published", res)
                drafts.ledger_add({"account_key": acct.key, "platform": p, "draft_id": draft_id,
                                   "post_id": res.get("post_id"), "post_ids": res.get("post_ids"),
                                   "url": res.get("url"), "topic": d.get("topic"),
                                   "followup": d["outputs"][p].get("buzz_followup") if isinstance(d["outputs"][p], dict) else None})
        except Exception as e:  # 1媒体の失敗で他を止めない。状態は進めない
            results[p] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:500]}
    return {"draft_id": draft_id, "dry_run": dry, "results": results}
