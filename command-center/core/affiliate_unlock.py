"""眠っている A8 案件の解放と、SNS → 自前WP記事 → 広告リンク のクッション導線。

背景（2026-11-08 実測）:
  マスターの A8 参加中 116 件のうち、広告コード（affiliate_url）が入っているのは 3 件だけ。
  残り 113 件は「登録媒体URLが違う」のではなく、広告コード自体が未取得で媒体も紐付いていなかった。

a8mat の構造（A8 管理画面「広告リンク作成」で 媒体001〜008 を切り替えて実測）:
  a8mat=<案件側のブロック>+<媒体×案件ごとのコード>+<広告主番号×10 の36進>+<素材コード>
    例 プログリット: 媒体001 → 4BA75B+4S2ALU+3NP4 ／ 媒体002 → 4BA75B+4S2BDM+3NP4 …
  1番目のブロックは全媒体で同じ。媒体で変わるのは2番目だけ。
  → どの媒体のコードかは、管理画面で取った媒体別コードと2番目のブロックを突き合わせて初めて決まる。

正本は管理画面のコード（data/affiliate/a8_console_codes.json、`import-a8-codes` で取り込む）。
公開記事のタグ（`affiliate-harvest`）は「どの案件をどのWPで使っているか」と「媒体ずれ」の検出にだけ使う。
広告リンクは一度もクリックしない。
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

import requests

from core import config as C

A8MAT = re.compile(r"https?://px\.a8\.net/svt/ejp\?a8mat=([0-9A-Z]+)\+([0-9A-Z]+)\+([0-9A-Z]+)\+([0-9A-Z]+)")
HARVEST_PATH = ("affiliate", "harvested_a8.json")
CONSOLE_PATH = ("affiliate", "a8_console_codes.json")


def decode_a8(href: str) -> dict | None:
    m = A8MAT.search(href or "")
    if not m:
        return None
    adv10 = int(m.group(3), 36)
    return {"block1": m.group(1), "partner_code": m.group(2), "advertiser": adv10 // 10 if adv10 % 10 == 0 else None,
            "creative": m.group(4), "href": m.group(0)}


# ---------------------------------------------------------------- 管理画面の媒体別コード（正本）
def import_console_codes(rows: list[list], fetched_at: str | None = None) -> dict:
    """ブラウザで取った [program_id, media_id, "B1_B2_B3_B4", material, options, sns] の配列を保存する。"""
    codes: dict[str, dict[str, dict]] = defaultdict(dict)
    for pid, mid, code, material, opts, sns in rows:
        if not code:
            continue
        parts = code.split("_")
        codes[pid][mid] = {"href": "https://px.a8.net/svt/ejp?a8mat=" + "+".join(parts), "partner_code": parts[1],
                           "material": material, "media_options": opts.split(",") if opts else [], "sns_link": bool(sns)}
    out = {"fetched_at": fetched_at or C.now_iso(), "source": "A8 media-console /program/create-link（媒体001〜008）",
           "codes": codes}
    C.write_json(C.data_path(*CONSOLE_PATH), out)
    return out


def console_codes() -> dict[str, dict[str, dict]]:
    return (C.read_json(C.data_path(*CONSOLE_PATH), {}) or {}).get("codes", {})


def wp_media_id(master: dict, wp_url: str | None) -> str | None:
    from core.account_loader import url_within

    if not wp_url:
        return None
    for rm in master.get("asp_inventory", {}).get("a8", {}).get("registered_media", []):
        if rm.get("registered_url") and url_within(wp_url, rm["registered_url"]) and url_within(rm["registered_url"], wp_url):
            return rm["media_id"]
    return None


# ---------------------------------------------------------------- 公開記事のタグ（使用状況・媒体ずれの検出）
def own_wp_sites(master: dict) -> list[tuple[str, str]]:
    from core.account_loader import get_accounts

    return [(a.key, a.platform("wordpress")["url"]) for a in get_accounts(master) if a.platform("wordpress").get("url")]


def harvest(master: dict, timeout: int = 30) -> dict[str, Any]:
    """自分の WP の公開記事（REST, 未ログイン）から A8 広告タグを集める。クリックはしない。"""
    rows = []
    for key, base in own_wp_sites(master):
        base = base.rstrip("/")
        for kind in ("posts", "pages"):
            page = 1
            while True:
                try:
                    r = requests.get(f"{base}/wp-json/wp/v2/{kind}", timeout=timeout,
                                     params={"per_page": 100, "page": page, "_fields": "id,link,content"})
                except requests.RequestException:
                    break
                if r.status_code != 200:
                    break
                data = r.json()
                for p in data:
                    for m in A8MAT.finditer(p["content"]["rendered"]):
                        rows.append({"account_key": key, "site": base + "/", "page": p["link"], **decode_a8(m.group(0))})
                if len(data) < 100:
                    break
                page += 1
    out = {"harvested_at": C.now_iso(), "rows": rows}
    C.write_json(C.data_path(*HARVEST_PATH), out)
    return out


def load_harvest() -> dict:
    return C.read_json(C.data_path(*HARVEST_PATH), {}) or {}


def check_harvest(master: dict, harvested: dict | None = None, codes: dict | None = None) -> list[dict]:
    """公開記事のタグを、管理画面の媒体別コードと完全一致で照合する。"""
    harvested = harvested if harvested is not None else load_harvest()
    codes = codes if codes is not None else console_codes()
    by_partner = {}
    for pid, per in codes.items():
        for mid, c in per.items():
            by_partner[c["partner_code"]] = (pid, mid)
    a8 = {p["program_id"]: p for p in master.get("asp_inventory", {}).get("a8", {}).get("programs", [])}
    groups: dict[tuple, dict] = {}
    for r in harvested.get("rows", []):
        k = (r["site"], r["partner_code"])
        g = groups.setdefault(k, {"account_key": r["account_key"], "site": r["site"], "partner_code": r["partner_code"],
                                  "advertiser": r["advertiser"], "href": r["href"], "pages": set()})
        g["pages"].add(r["page"])
    out = []
    for g in groups.values():
        site_mid = wp_media_id(master, g["site"])
        hit = by_partner.get(g["partner_code"])
        rec = {**g, "pages": sorted(g["pages"]), "site_media_id": site_mid}
        if not hit:
            rec["state"] = "not_in_console"
            rec["reason"] = "参加中116件のどの媒体のコードとも一致しない（提携終了・別アカウント・古いコードの可能性）"
        else:
            pid, mid = hit
            rec.update(program_id=pid, program_name=a8.get(pid, {}).get("program_name"), code_media_id=mid)
            if mid == site_mid:
                rec["state"], rec["reason"] = "ok", "このWPの媒体のコード"
            else:
                rec["state"], rec["reason"] = "media_mismatch", f"媒体{mid}のコードが媒体{site_mid}のWPに貼られている"
        out.append(rec)
    return out


# ---------------------------------------------------------------- ルーティング
def assigned_programs(account, master: dict) -> set[str]:
    """このアカウントのWPで使う案件: Astra の matched_affiliates ＋ 本人がそのWPの公開記事で既に使っている案件。"""
    ids = {p.get("program_id") for p in account.monetize.get("matched_affiliates") or [] if p.get("asp_name", "").startswith("A8")}
    for r in check_harvest(master):
        if r["account_key"] == account.key and r.get("program_id"):
            ids.add(r["program_id"])
    return {i for i in ids if i}


def recovered_programs(account, master: dict, settings: dict) -> list[dict]:
    """affiliate_pool に足す A8 案件。広告コードは管理画面で取った、このWPの媒体向けのものだけを使う。"""
    if not (settings.get("affiliate", {}) or {}).get("use_console_codes", True):
        return []
    wp = account.platform("wordpress").get("url")
    mid = wp_media_id(master, wp)
    codes = console_codes()
    if not mid or not codes:
        return []
    a8 = {p["program_id"]: p for p in master.get("asp_inventory", {}).get("a8", {}).get("programs", [])}
    out = []
    for pid in sorted(assigned_programs(account, master)):
        c = codes.get(pid, {}).get(mid)
        if not c or pid not in a8:
            continue
        p = a8[pid]
        out.append({"asp_name": "A8.net", "program_id": pid, "program_name": p["program_name"],
                    "unit_price": p.get("unit_price"), "affiliate_url": c["href"], "affiliate_url_media_id": mid,
                    "status": p.get("status"), "landing_page_url": p.get("landing_page_url"),
                    "appeal_point": p.get("appeal_point"), "conversion_conditions": p.get("conversion_conditions"),
                    "fit_warning": p.get("fit_warning") or "成果条件・LPは未取得。本文で条件や効果を断定しない",
                    "code_source": "a8_console", "sns_link_available": c["sns_link"]})
    return out


def audit(master: dict, settings: dict) -> dict[str, Any]:
    """A8 116件の内訳と、クッション導線で使える案件数。"""
    from core.account_loader import affiliate_pool, get_accounts

    a8 = master.get("asp_inventory", {}).get("a8", {}).get("programs", [])
    codes = console_codes()
    accounts = get_accounts(master)
    assigned = {}
    for a in accounts:
        if wp_media_id(master, a.platform("wordpress").get("url")):
            for pid in assigned_programs(a, master):
                assigned.setdefault(pid, []).append(a.key)
    breakdown = defaultdict(list)
    for p in a8:
        pid = p["program_id"]
        if not codes.get(pid):
            k = "no_console_code"
        elif pid in assigned:
            k = "console_code_assigned_to_own_wp"
        else:
            k = "console_code_no_account_assigned"
        breakdown[k].append(pid)
    per_account = {}
    for a in accounts:
        wp = a.platform("wordpress").get("url")
        sns = [p for p in a.active_platforms() if p != "wordpress"]
        direct = {p: sorted({x["program_id"] for x in affiliate_pool(a, a.platform(p).get("url"), settings) if x["usable"]})
                  for p in sns}
        via_wp = sorted({x["program_id"] for x in affiliate_pool(a, wp, settings) if x["usable"]}) if wp and a.is_active("wordpress") else []
        per_account[a.key] = {"wordpress": wp, "wp_media_id": wp_media_id(master, wp), "sns_platforms": sns,
                              "direct_on_sns": direct, "via_wp_cushion": via_wp, "count_via_wp": len(via_wp)}
    sns_ok = sorted(pid for pid, per in codes.items() if any(c["sns_link"] for c in per.values()))
    return {"a8_total": len(a8), "console_fetched_at": (C.read_json(C.data_path(*CONSOLE_PATH), {}) or {}).get("fetched_at"),
            "breakdown": {k: len(v) for k, v in breakdown.items()}, "breakdown_ids": dict(breakdown),
            "sns_note_link_available": len(sns_ok), "harvest_checks": check_harvest(master), "per_account": per_account}
