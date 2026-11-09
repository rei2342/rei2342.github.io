"""accounts_master.json（Astra出力）を唯一の情報源として読み、媒体ルーティングを決める。

アカウント名・媒体構成はコードに一切書かない。
- 稼働媒体 = status == "active" かつ URL がある媒体（unverified は skip: automation_contract準拠）
- 書き込み可否 = settings.yaml の publishing.enabled ＋ 認証情報の有無（マスターは読み取り専用の契約）
- アフィリンク = 登録媒体URLと配信先URLが一致する案件だけ（media_link_behavior準拠）
"""
from __future__ import annotations

import copy
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from core import config as C

PLATFORM_ORDER = ["wordpress", "note", "x", "threads", "instagram"]
FORMAT_BY_PLATFORM = {
    "wordpress": "wp_html",
    "note": "note_md",
    "x": "x_thread",
    "threads": "threads_tree",
    "instagram": "ig_carousel",
}
PLATFORM_LABEL = {
    "wordpress": "WordPress",
    "note": "note",
    "x": "X",
    "threads": "Threads",
    "instagram": "Instagram",
}


# ---------------------------------------------------------------- master I/O
def load_master(path: Path = C.MASTER_PATH) -> dict[str, Any]:
    m = C.read_json(path)
    if m is None:
        raise FileNotFoundError(f"{path} が無いか壊れている。Astra の出力を置くかダッシュボードからインポートする。")
    validate_master(m)
    return m


def validate_master(m: dict[str, Any]) -> list[str]:
    """致命的な欠落は例外、軽微なものは警告リストを返す。"""
    if not isinstance(m, dict) or not isinstance(m.get("accounts"), list):
        raise ValueError("accounts 配列が無い。Astra の accounts_master.json 形式ではない。")
    warnings: list[str] = []
    seen = set()
    for i, a in enumerate(m["accounts"]):
        k = a.get("internal_key")
        if not k:
            raise ValueError(f"accounts[{i}] に internal_key が無い")
        if k in seen:
            raise ValueError(f"internal_key が重複: {k}")
        seen.add(k)
        if not isinstance(a.get("platforms"), dict):
            raise ValueError(f"{k}: platforms が無い")
        for p, v in a["platforms"].items():
            if v.get("status") == "active" and not v.get("url"):
                warnings.append(f"{k}.{p}: active なのに url が無い → 稼働対象から外す")
    return warnings


def save_master(m: dict[str, Any], note: str = "") -> Path:
    validate_master(m)
    hist = C.CONFIG_DIR / "history"
    hist.mkdir(exist_ok=True)
    backup = None
    if C.MASTER_PATH.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = hist / f"accounts_master.{stamp}.json"
        shutil.copy2(C.MASTER_PATH, backup)
    C.write_json(C.MASTER_PATH, m)
    C.append_jsonl(hist / "changes.jsonl", {"at": C.now_iso(), "note": note, "backup": str(backup) if backup else None})
    return C.MASTER_PATH


def diff_masters(old: dict, new: dict) -> list[dict]:
    """アカウント×媒体単位の差分（ダッシュボードのインポート前確認用）。"""
    rows = []
    o = {a["internal_key"]: a for a in old.get("accounts", [])}
    n = {a["internal_key"]: a for a in new.get("accounts", [])}
    for k in sorted(set(o) | set(n)):
        if k not in o:
            rows.append({"account": k, "platform": "*", "field": "account", "old": None, "new": "追加"})
            continue
        if k not in n:
            rows.append({"account": k, "platform": "*", "field": "account", "old": "存在", "new": "削除"})
            continue
        for p in sorted(set(o[k]["platforms"]) | set(n[k]["platforms"])):
            ov, nv = o[k]["platforms"].get(p, {}), n[k]["platforms"].get(p, {})
            for f in ("handle", "url", "status", "domain", "display_name"):
                if ov.get(f) != nv.get(f):
                    rows.append({"account": k, "platform": p, "field": f, "old": ov.get(f), "new": nv.get(f)})
    return rows


def import_master(new: dict[str, Any], mode: str = "replace", note: str = "import") -> tuple[dict, list[str]]:
    """mode=replace: 丸ごと差し替え / merge: internal_key 単位で上書き・追加（既存の他アカウントは残す）。"""
    warnings = validate_master(new)
    if mode == "merge" and C.MASTER_PATH.exists():
        cur = load_master()
        merged = copy.deepcopy(cur)
        idx = {a["internal_key"]: i for i, a in enumerate(merged["accounts"])}
        for a in new["accounts"]:
            if a["internal_key"] in idx:
                merged["accounts"][idx[a["internal_key"]]] = a
            else:
                merged["accounts"].append(a)
        for top in ("asp_inventory", "automation_contract", "status_semantics", "coverage", "sources"):
            if top in new:
                if isinstance(new[top], dict) and isinstance(merged.get(top), dict):
                    merged[top] = {**merged[top], **new[top]}
                else:
                    merged[top] = new[top]
        for top in ("schema_version", "generated_at", "research_date"):
            if top in new:
                merged[top] = new[top]
        new = merged
    elif C.MASTER_PATH.exists() and "candidate_notes" not in new:
        # 人が確定した discover 候補メモは Astra の差し替えで消さない
        cur_notes = load_master().get("candidate_notes")
        if cur_notes:
            new = {**new, "candidate_notes": cur_notes}
    save_master(new, note=f"{note} ({mode})")
    return new, warnings


# ---------------------------------------------------------------- account model
@dataclass
class RouteEntry:
    platform: str
    format: str
    url: str | None
    handle: str | None
    status: str
    readable: bool          # クロール・生成の対象
    write_enabled: bool     # settings で書き込み許可済み
    has_credentials: bool
    reason: str

    @property
    def can_publish(self) -> bool:
        return self.readable and self.write_enabled and self.has_credentials


@dataclass
class Account:
    raw: dict[str, Any]
    master: dict[str, Any] = field(repr=False)

    @property
    def key(self) -> str:
        return self.raw["internal_key"]

    @property
    def label(self) -> str:
        return self.raw.get("label") or self.key

    @property
    def platforms(self) -> dict[str, dict]:
        return self.raw.get("platforms", {})

    @property
    def persona(self) -> dict:
        return self.raw.get("extracted_persona", {}) or {}

    @property
    def monetize(self) -> dict:
        return self.raw.get("monetize_strategy", {}) or {}

    @property
    def assets(self) -> list[dict]:
        return self.raw.get("additional_assets") or []

    @property
    def conflicts(self) -> list[str]:
        return self.raw.get("conflicts_and_limits") or []

    def platform(self, p: str) -> dict:
        return self.platforms.get(p, {}) or {}

    def is_active(self, p: str) -> bool:
        v = self.platform(p)
        return v.get("status") == "active" and bool(v.get("url"))

    def active_platforms(self) -> list[str]:
        return [p for p in PLATFORM_ORDER if self.is_active(p)] + [
            p for p in self.platforms if p not in PLATFORM_ORDER and self.is_active(p)
        ]

    def handle(self, p: str) -> str | None:
        h = self.platform(p).get("handle")
        return h.lstrip("@") if h else None

    def own_destinations(self) -> list[dict]:
        """SNSからの誘導先として使える自分の資産（note/WP/LINE/診断など）。"""
        out = []
        for p in ("wordpress", "note"):
            if self.is_active(p):
                out.append({"type": p, "url": self.platform(p)["url"], "label": PLATFORM_LABEL[p]})
        for a in self.assets:
            url = a.get("url")
            st = str(a.get("status", ""))
            if not url or "prelaunch" in st or "unverified" in st and a.get("type") != "line":
                continue
            out.append({"type": a.get("type"), "url": url, "label": a.get("label") or a.get("type"), "status": st})
        extra = ((C.load_settings().get("funnel") or {}).get("extra_destinations") or {}).get(self.key) or []
        for e in extra:  # 人が settings で明示した誘導先（ローンチ後のLINEなど）
            e = {"url": e} if isinstance(e, str) else e
            out.append({"type": e.get("type", "manual"), "url": e["url"], "label": e.get("label", "settings")})
        for prod in self.monetize.get("verified_existing_products") or []:
            if prod.get("url"):
                out.append({"type": "note_product", "url": prod["url"], "label": prod.get("title"), "price_jpy": prod.get("price_jpy")})
        return out

    def calibration(self) -> dict:
        return C.read_json(C.DATA_DIR / "calibration" / f"{self.key}.json", {}) or {}

    def route(self, settings: dict | None = None) -> list[RouteEntry]:
        s = settings or C.load_settings()
        enabled = (s.get("publishing", {}).get("enabled") or {}).get(self.key, {}) or {}
        rows = []
        for p in PLATFORM_ORDER + [x for x in self.platforms if x not in PLATFORM_ORDER]:
            v = self.platform(p)
            if not v:
                continue
            active = self.is_active(p)
            creds = C.has_creds(p, self.key, s)
            we = bool(enabled.get(p))
            if not active:
                reason = v.get("reason") or f"status={v.get('status')} → 稼働対象外"
            elif not we:
                reason = "生成のみ（settings.yaml publishing.enabled で未許可）"
            elif not creds:
                reason = "許可済みだが認証情報が未設定（config/.env）"
            else:
                reason = "配信可能"
            rows.append(RouteEntry(p, FORMAT_BY_PLATFORM.get(p, p), v.get("url"), v.get("handle"),
                                   v.get("status", "unknown"), active, we, creds, reason))
        return rows

    def funnel_summary(self) -> str:
        return self.monetize.get("primary_funnel") or ""


def get_accounts(master: dict | None = None) -> list[Account]:
    m = master or load_master()
    return [Account(a, m) for a in m["accounts"]]


def get_account(key_or_label: str, master: dict | None = None) -> Account:
    for a in get_accounts(master):
        if key_or_label in (a.key, a.label):
            return a
    raise KeyError(f"アカウントが見つからない: {key_or_label}")


# ---------------------------------------------------------------- affiliate guard
def _norm(url: str) -> str:
    u = urlparse(url if "://" in url else "https://" + url.lstrip("/"))
    host = (u.netloc or "").lower().removeprefix("www.")
    return host + (u.path or "/").rstrip("/")


def url_within(target: str, registered: str) -> bool:
    t, r = _norm(target), _norm(registered)
    return t == r or t.startswith(r + "/") or (r.count("/") == 0 and t.split("/")[0] == r)


def registered_media_url(program: dict, master: dict, settings: dict) -> str | None:
    if program.get("affiliate_url_media_id"):
        for rm in master.get("asp_inventory", {}).get("a8", {}).get("registered_media", []):
            if rm.get("media_id") == program["affiliate_url_media_id"]:
                return rm.get("registered_url")
    if program.get("registered_media_id"):
        return (settings.get("affiliate", {}).get("moshimo_media_map") or {}).get(str(program["registered_media_id"]))
    return None


def affiliate_pool(account: Account, target_url: str | None, settings: dict | None = None,
                   for_auto_publish: bool = False) -> list[dict]:
    """配信先URLに対して使える案件を判定付きで返す。URLは原文のまま保持する。"""
    s = settings or C.load_settings()
    overrides = set(s.get("affiliate", {}).get("auto_publish_overrides") or [])
    out = []
    from core import affiliate_unlock

    matched = list(account.monetize.get("matched_affiliates") or [])
    recovered = {p["program_id"]: p for p in affiliate_unlock.recovered_programs(account, account.master, s)}
    # マスターで広告コードが空の案件は、公開記事から戻したコードで埋める（Astra の訴求・条件は残す）
    for i, p in enumerate(matched):
        rp = recovered.pop(p.get("program_id"), None)
        if rp and not p.get("affiliate_url"):
            matched[i] = {**p, **{k: rp[k] for k in ("affiliate_url", "affiliate_url_media_id", "code_source")},
                          "fit_warning": p.get("fit_warning") or rp["fit_warning"]}
    matched += list(recovered.values())
    for prog in matched:
        url = prog.get("affiliate_url")
        reg = registered_media_url(prog, account.master, s)
        usable, reason = True, "OK"
        if not url:
            usable, reason = False, "affiliate_url が null（広告コード未取得）"
        elif "historical" in str(prog.get("status", "")):
            usable, reason = False, "過去記録（現行提携ではない）"
        elif not reg:
            usable, reason = False, "登録媒体URLを特定できない（moshimo_media_map 未記入）"
        elif not target_url or not url_within(target_url, reg):
            usable, reason = False, f"登録媒体 {reg} 以外の配信先には流用不可"
        elif for_auto_publish and not prog.get("auto_publish_allowed") and prog.get("program_id") not in overrides:
            usable, reason = False, "auto_publish_allowed=false（人の承認が必要）"
        out.append({
            "program_id": prog.get("program_id"),
            "program_name": prog.get("program_name"),
            "asp_name": prog.get("asp_name"),
            "unit_price": prog.get("unit_price"),
            "affiliate_url": url,
            "landing_page_url": prog.get("landing_page_url"),
            "appeal_point": prog.get("appeal_point"),
            "conversion_conditions": prog.get("conversion_conditions"),
            "fit_warning": prog.get("fit_warning"),
            "code_source": prog.get("code_source", "master"),
            "registered_media_url": reg,
            "usable": usable,
            "reason": reason,
        })
    return out


# ---------------------------------------------------------------- dashboard helpers
def flatten(master: dict | None = None, settings: dict | None = None) -> list[dict]:
    s = settings or C.load_settings()
    rows = []
    for a in get_accounts(master):
        for r in a.route(s):
            rows.append({
                "account": a.label,
                "internal_key": a.key,
                "platform": r.platform,
                "handle": r.handle,
                "url": r.url,
                "status": r.status,
                "verification": a.platform(r.platform).get("verification_status"),
                "write_enabled": r.write_enabled,
                "credentials": r.has_credentials,
                "route": r.reason,
            })
    return rows


def apply_table_edits(rows: list[dict], note: str = "dashboard edit") -> int:
    """ダッシュボードの編集表（handle/url/status）をマスターへ書き戻す。変更件数を返す。"""
    m = load_master()
    idx = {a["internal_key"]: a for a in m["accounts"]}
    changed = 0
    for r in rows:
        a = idx.get(r["internal_key"])
        if not a:
            continue
        p = a["platforms"].setdefault(r["platform"], {})
        for f in ("handle", "url", "status"):
            v = r.get(f)
            v = None if v in ("", "None") else v
            if p.get(f) != v:
                p[f] = v
                if f in ("handle", "url") and v:
                    p["verification_status"] = "user_edited"
                changed += 1
    if changed:
        save_master(m, note=note)
    return changed


def set_write_enabled(key: str, platform: str, value: bool) -> None:
    s = C.load_settings()
    pub = s.setdefault("publishing", {})
    en = pub.get("enabled") or {}
    en.setdefault(key, {})[platform] = bool(value)
    pub["enabled"] = en
    C.save_settings(s)
