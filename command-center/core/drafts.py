"""下書き・承認・配信台帳。draft → approved → published（媒体ごと）。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from core import config as C

DRAFT_DIR = C.DATA_DIR / "drafts"
LEDGER = C.DATA_DIR / "ledger" / "posts.jsonl"


def new_id(account_key: str) -> str:
    return f"{account_key}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def path(draft_id: str) -> Path:
    return DRAFT_DIR / f"{draft_id}.json"


def save(d: dict[str, Any]) -> dict[str, Any]:
    d["updated_at"] = C.now_iso()
    C.write_json(path(d["id"]), d)
    return d


def get(draft_id: str) -> dict[str, Any]:
    d = C.read_json(path(draft_id))
    if not d:
        raise KeyError(f"下書きが無い: {draft_id}")
    return d


def list_all(account_key: str | None = None) -> list[dict]:
    if not DRAFT_DIR.exists():
        return []
    out = []
    for p in sorted(DRAFT_DIR.glob("*.json"), reverse=True):
        d = C.read_json(p)
        if d and (account_key is None or d.get("account_key") == account_key):
            out.append(d)
    return out


def approve(draft_id: str, platforms: list[str] | None = None, by: str = "human") -> dict:
    d = get(draft_id)
    from core.guards import has_errors

    targets = platforms or list(d.get("outputs", {}).keys())
    blocked = [i for i in d.get("issues", []) if i["level"] == "error" and i["platform"] in targets]
    if blocked:
        raise ValueError("error 判定が残っている媒体は承認できない: " + "; ".join(f"{i['platform']}:{i['msg']}" for i in blocked[:5]))
    st = d.setdefault("platform_status", {})
    for p in targets:
        if st.get(p) != "published":
            st[p] = "approved"
    d.setdefault("history", []).append({"at": C.now_iso(), "event": "approved", "platforms": targets, "by": by})
    return save(d)


def mark(draft_id: str, platform: str, status: str, result: dict | None = None) -> dict:
    d = get(draft_id)
    d.setdefault("platform_status", {})[platform] = status
    d.setdefault("results", {})[platform] = result or {}
    d.setdefault("history", []).append({"at": C.now_iso(), "event": status, "platform": platform, "result": result})
    return save(d)


def ledger_add(entry: dict) -> None:
    C.append_jsonl(LEDGER, {"at": C.now_iso(), **entry})


def ledger() -> list[dict]:
    return C.read_jsonl(LEDGER)
