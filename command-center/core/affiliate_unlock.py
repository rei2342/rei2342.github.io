"""眠っている A8 案件の解放と、SNS → 自前WP記事 → 広告リンク のクッション導線。

背景（2026-11-08 実測）:
  マスターの A8 参加中 116 件のうち、広告コード（affiliate_url）が入っているのは 3 件だけ。
  残り 113 件は「登録媒体URLが違う」のではなく、広告コード自体が未取得で媒体も紐付いていない。
  ただし自分の WP の公開記事には、既に A8 管理画面で発行した広告タグが大量に貼られている。

a8mat の構造（マスターで媒体確認済みの3件＋ARE DB の6件で検算済み）:
  a8mat=<媒体コード>+<提携コード>+<広告主番号×10 を36進>+<素材コード>
    例 4BA75B+4S2ALU+3NP4+5YRHE → 3NP4 = 170680 → 広告主 17068 → s00000017068001 プログリット
  媒体コード → 媒体ID は、マスターで媒体確認済みの案件から逆引きする（推測で足さない）。

ここでは「媒体コードが確認済み媒体のもの」かつ「その媒体の登録URLの記事に貼られている」
かつ「マスターの参加中一覧に広告主が1件だけ該当する」ものだけを使える案件に戻す。
広告リンクは一度もクリックしない（成果・クリック数を汚さない）。
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

import requests

from core import config as C

A8MAT = re.compile(r"https?://px\.a8\.net/svt/ejp\?a8mat=([0-9A-Z]+)\+([0-9A-Z]+)\+([0-9A-Z]+)\+([0-9A-Z]+)")
HARVEST_PATH = ("affiliate", "harvested_a8.json")


def decode_a8(href: str) -> dict | None:
    m = A8MAT.search(href or "")
    if not m:
        return None
    adv10 = int(m.group(3), 36)
    return {"media_code": m.group(1), "partner_code": m.group(2), "advertiser": adv10 // 10 if adv10 % 10 == 0 else None,
            "creative": m.group(4), "href": m.group(0)}


def media_code_map(master: dict) -> dict[str, str]:
    """媒体コード → A8 媒体ID。マスターで媒体確認済みの広告コードからだけ作る。"""
    out = {}
    for p in master.get("asp_inventory", {}).get("a8", {}).get("programs", []):
        d = decode_a8(p.get("affiliate_url") or "")
        if d and p.get("affiliate_url_media_id"):
            out[d["media_code"]] = p["affiliate_url_media_id"]
    return out


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
                        d = decode_a8(m.group(0))
                        rows.append({"account_key": key, "site": base + "/", "page": p["link"], **d})
                if len(data) < 100:
                    break
                page += 1
    out = {"harvested_at": C.now_iso(), "rows": rows}
    C.write_json(C.data_path(*HARVEST_PATH), out)
    return out


def load_harvest() -> dict:
    return C.read_json(C.data_path(*HARVEST_PATH), {}) or {}


def resolve(master: dict, harvested: dict | None = None) -> dict[str, Any]:
    """集めたタグを、媒体・広告主・参加中一覧で照合して分類する。"""
    from core.account_loader import url_within

    harvested = harvested if harvested is not None else load_harvest()
    a8 = master.get("asp_inventory", {}).get("a8", {})
    media = {m["media_id"]: m for m in a8.get("registered_media", [])}
    codes = media_code_map(master)
    by_adv: dict[int, list[dict]] = defaultdict(list)
    for p in a8.get("programs", []):
        if re.fullmatch(r"s\d{11}\d{3}", p["program_id"] or ""):
            by_adv[int(p["program_id"][1:-3])].append(p)
    groups: dict[tuple, dict] = {}
    for r in harvested.get("rows", []):
        k = (r["site"], r["media_code"], r["partner_code"], r["advertiser"])
        g = groups.setdefault(k, {**{f: r[f] for f in ("account_key", "site", "media_code", "partner_code", "advertiser")},
                                  "hrefs": defaultdict(int), "pages": set()})
        g["hrefs"][r["href"]] += 1
        g["pages"].add(r["page"])
    resolved, flags = [], []
    for g in groups.values():
        mid = codes.get(g["media_code"])
        reg = media.get(mid, {}).get("registered_url") if mid else None
        cands = by_adv.get(g["advertiser"] or -1, [])
        # 提携コードが一致する既知コードがあれば、同じ広告主の中のどの案件かまで決まる
        exact = [p for p in cands if (decode_a8(p.get("affiliate_url") or "") or {}).get("partner_code") == g["partner_code"]]
        if exact:
            cands = exact
        rec = {"account_key": g["account_key"], "site": g["site"], "media_code": g["media_code"], "media_id": mid,
               "registered_media_url": reg, "advertiser": g["advertiser"],
               "href": max(g["hrefs"], key=g["hrefs"].get), "pages": sorted(g["pages"]),
               "candidates": [{"program_id": p["program_id"], "program_name": p["program_name"]} for p in cands]}
        if not mid:
            rec["state"], rec["reason"] = "media_unverified", f"媒体コード {g['media_code']} がどの登録媒体か未確認（A8管理画面で要確認）"
        elif not url_within(g["site"], reg):
            rec["state"], rec["reason"] = "media_mismatch", f"媒体 {mid}（{reg}）のコードが {g['site']} に貼られている"
        elif not cands:
            rec["state"], rec["reason"] = "not_partnered", "参加中一覧（2026-11-07）に広告主が無い。提携終了の可能性"
        elif len(cands) > 1:
            rec["state"], rec["reason"] = "ambiguous", "同じ広告主に複数の案件があり、どれのコードか決まらない"
        else:
            rec["state"], rec["reason"] = "usable", "確認済み媒体のコードを、その媒体の公開記事から原文取得"
            rec["program_id"] = cands[0]["program_id"]
        (resolved if rec["state"] == "usable" else flags).append(rec)
    return {"usable": resolved, "flags": flags}


def recovered_programs(account_key: str, master: dict, settings: dict) -> list[dict]:
    """affiliate_pool に足す、公開記事から戻した案件（マスターに広告コードが無いものだけ）。"""
    if not (settings.get("affiliate", {}) or {}).get("use_harvested_codes", True):
        return []
    a8 = {p["program_id"]: p for p in master.get("asp_inventory", {}).get("a8", {}).get("programs", [])}
    out, seen = [], set()
    for r in resolve(master)["usable"]:
        pid = r["program_id"]
        if r["account_key"] != account_key or pid in seen or a8.get(pid, {}).get("affiliate_url"):
            continue
        seen.add(pid)
        p = a8[pid]
        out.append({"asp_name": "A8.net", "program_id": pid, "program_name": p["program_name"],
                    "unit_price": p.get("unit_price"), "affiliate_url": r["href"], "affiliate_url_media_id": r["media_id"],
                    "status": p.get("status"), "landing_page_url": None, "appeal_point": None, "conversion_conditions": None,
                    "fit_warning": "公開記事から戻した広告コード。成果条件・LPは未取得なので、本文で条件や効果を断定しない",
                    "code_source": "own_live_article", "code_pages": r["pages"][:3]})
    return out


def audit(master: dict, settings: dict) -> dict[str, Any]:
    """A8 116件の内訳と、クッション導線で使える案件数。"""
    from core.account_loader import affiliate_pool, get_accounts

    a8 = master.get("asp_inventory", {}).get("a8", {}).get("programs", [])
    res = resolve(master)
    usable_ids = {r["program_id"] for r in res["usable"]}
    flagged_adv = defaultdict(list)
    for f in res["flags"]:
        for c in f["candidates"]:
            flagged_adv[c["program_id"]].append(f["state"])
    breakdown = defaultdict(list)
    for p in a8:
        pid = p["program_id"]
        if p.get("affiliate_url"):
            k = "code_in_master"
        elif pid in usable_ids:
            k = "recovered_from_own_article"
        elif flagged_adv.get(pid):
            k = "code_found_" + sorted(set(flagged_adv[pid]))[0]
        else:
            k = "no_code_anywhere"
        breakdown[k].append(pid)
    per_account = {}
    for a in get_accounts(master):
        wp = a.platform("wordpress").get("url")
        sns = [p for p in a.active_platforms() if p != "wordpress"]
        direct = {p: sorted({x["program_id"] for x in affiliate_pool(a, a.platform(p).get("url"), settings) if x["usable"]})
                  for p in sns}
        via_wp = sorted({x["program_id"] for x in affiliate_pool(a, wp, settings) if x["usable"]}) if wp and a.is_active("wordpress") else []
        per_account[a.key] = {"wordpress": wp, "sns_platforms": sns, "direct_on_sns": direct,
                              "via_wp_cushion": via_wp, "count_via_wp": len(via_wp)}
    return {"a8_total": len(a8), "breakdown": {k: len(v) for k, v in breakdown.items()},
            "breakdown_ids": dict(breakdown), "flags": res["flags"], "per_account": per_account}
