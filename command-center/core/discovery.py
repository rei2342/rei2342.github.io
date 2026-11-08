"""フェーズ1: ローカル環境から実アカウントの痕跡を集める（読み取り専用）。

対象: ホーム配下のプロジェクト・ドキュメント・.env・設定ファイル・スクリプト、
      Chrome/Edge/Brave/Firefox の履歴・ブックマーク、Safari ブックマーク（権限があれば）。
出力: data/discovery/report.json。マスターは書き換えない（null を推測で埋めない契約）。
秘密値は保存しない。キー名と「値があるか」だけ記録する。
"""
from __future__ import annotations

import json
import os
import plistlib
import re
import shutil
import sqlite3
import tempfile
from collections import defaultdict
from pathlib import Path

from core import config as C
from core.account_loader import load_master

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".cache", ".npm", ".cargo", ".rustup", ".gradle",
             "Library", "Caches", ".Trash", "Applications", ".nix-defexpr", ".bun", "site-packages", "dist", "build", "Pictures",
             "Movies", "Music"}
EXTS = {".env", ".json", ".yaml", ".yml", ".md", ".py", ".toml", ".txt", ".ini", ".cfg", ".js", ".ts", ".csv", ".html", ".sh"}
MAX_BYTES = 2_000_000

PATTERNS = {
    "x": re.compile(r"(?:https?://)?(?:www\.)?(?:x|twitter)\.com/@?([A-Za-z0-9_]{3,15})(?![A-Za-z0-9_])"),
    "instagram": re.compile(r"(?:https?://)?(?:www\.)?instagram\.com/([A-Za-z0-9_.]{3,30})"),
    "threads": re.compile(r"(?:https?://)?(?:www\.)?threads\.(?:net|com)/@([A-Za-z0-9_.]{3,30})"),
    "note": re.compile(r"(?:https?://)?note\.com/([A-Za-z0-9_]{3,30})"),
    "line": re.compile(r"https?://(?:lin\.ee|line\.me/R/ti/p|liff\.line\.me)/[A-Za-z0-9@%_\-/]+"),
    "wordpress": re.compile(r"https?://([a-z0-9.\-]+\.[a-z]{2,})/(?:wp-json|wp-admin|wp-content)"),
}
NOT_HANDLES = {"home", "i", "intent", "share", "search", "explore", "settings", "login", "hashtag", "status", "p", "reel",
               "reels", "stories", "notes", "n", "m", "api", "info", "accounts", "web", "privacy", "about", "topics", "tos",
               "messages", "compose", "notifications", "signup", "legal", "help", "en", "ja"}
ENV_KEY_RE = re.compile(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]{2,})\s*=\s*(.*)$")
INTERESTING_KEYS = re.compile(r"(ANTHROPIC|OPENAI|WP_|WORDPRESS|X_|TWITTER|THREADS|IG_|INSTAGRAM|META_|FB_|NOTE_|LINE_|A8|MOSHIMO|AMAZON|RAKUTEN|AFB)")


def _iter_files(roots: list[Path]):
    for root in roots:
        if not root.exists():
            continue
        for dp, dns, fns in os.walk(root):
            dns[:] = [d for d in dns if d not in SKIP_DIRS and not d.startswith(".") or d in (".env", ".config", ".github")]
            for fn in fns:
                p = Path(dp) / fn
                if (p.suffix.lower() in EXTS or fn.startswith(".env")) and p.stat().st_size <= MAX_BYTES:
                    yield p


def _scan_text(text: str, src: str, found: dict):
    for plat, rx in PATTERNS.items():
        for m in rx.finditer(text):
            val = m.group(1) if m.groups() else m.group(0)
            if plat in ("x", "instagram", "note") and val.lower() in NOT_HANDLES:
                continue
            found[plat][val].add(src)


def _browser_dbs() -> list[tuple[str, Path]]:
    home = Path.home()
    cands = []
    bases = [home / "Library/Application Support/Google/Chrome", home / "Library/Application Support/Microsoft Edge",
             home / "Library/Application Support/BraveSoftware/Brave-Browser", home / ".config/google-chrome",
             home / ".config/chromium", home / "AppData/Local/Google/Chrome/User Data"]
    for b in bases:
        if b.exists():
            for prof in b.iterdir():
                if (prof / "History").exists():
                    cands.append(("chromium_history", prof / "History"))
                if (prof / "Bookmarks").exists():
                    cands.append(("chromium_bookmarks", prof / "Bookmarks"))
    for ff in [home / "Library/Application Support/Firefox/Profiles", home / ".mozilla/firefox"]:
        if ff.exists():
            for prof in ff.iterdir():
                if (prof / "places.sqlite").exists():
                    cands.append(("firefox_places", prof / "places.sqlite"))
    sb = home / "Library/Safari/Bookmarks.plist"
    if sb.exists():
        cands.append(("safari_bookmarks", sb))
    return cands


def _read_browser(kind: str, path: Path) -> str:
    if kind == "chromium_bookmarks":
        return path.read_text(encoding="utf-8", errors="ignore")
    if kind == "safari_bookmarks":
        try:
            return json.dumps(plistlib.loads(path.read_bytes()), default=str)
        except Exception:
            return ""
    with tempfile.TemporaryDirectory() as td:  # ロック回避のためコピーして読む
        tmp = Path(td) / "db"
        shutil.copy2(path, tmp)
        con = sqlite3.connect(tmp)
        q = "SELECT url FROM urls" if kind == "chromium_history" else "SELECT url FROM moz_places"
        q += " WHERE url LIKE '%x.com/%' OR url LIKE '%twitter.com/%' OR url LIKE '%instagram.com/%' OR url LIKE '%threads.%' " \
             "OR url LIKE '%note.com/%' OR url LIKE '%wp-admin%' OR url LIKE '%lin.ee%' OR url LIKE '%liff.line.me%'"
        try:
            rows = con.execute(q).fetchall()
        finally:
            con.close()
        return "\n".join(r[0] for r in rows)


def run(roots: list[str] | None = None, include_browser: bool = True) -> dict:
    roots_p = [Path(r).expanduser() for r in (roots or ["~"])]
    found: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    env_keys: dict[str, dict] = {}
    scanned = 0
    try:
        known_handles = {(v.get("handle") or "").lstrip("@") for a in load_master()["accounts"]
                         for v in a["platforms"].values() if v.get("handle")}
    except Exception:
        known_handles = set()
    mention_re = re.compile(r"@(" + "|".join(re.escape(h) for h in sorted(known_handles, key=len, reverse=True)) + r")(?![A-Za-z0-9_])") \
        if known_handles else None
    for p in _iter_files(roots_p):
        if str(p).startswith(str(C.ROOT)):
            continue  # このシステム自身（Astraのマスター・生成物）は除外し、既存の痕跡だけを見る
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        scanned += 1
        _scan_text(text, str(p), found)
        if mention_re:
            for m in mention_re.finditer(text):
                found["mention"][m.group(1)].add(str(p))
        if p.name.startswith(".env") or p.suffix in (".env", ".sh", ".toml", ".ini"):
            for line in text.splitlines():
                m = ENV_KEY_RE.match(line)
                if m and INTERESTING_KEYS.search(m.group(1)):
                    v = m.group(2).strip().strip("'\"")
                    placeholder = (not v) or "your" in v.lower() or v.endswith("here") or v in ("xxx", "...")
                    env_keys.setdefault(m.group(1), {"files": [], "has_real_value": False})
                    env_keys[m.group(1)]["files"].append(str(p))
                    env_keys[m.group(1)]["has_real_value"] |= not placeholder
        for m in re.finditer(r"secrets\.([A-Z][A-Z0-9_]+)", text):
            env_keys.setdefault(m.group(1), {"files": [], "has_real_value": False})
            env_keys[m.group(1)]["github_secret"] = True
            if str(p) not in env_keys[m.group(1)]["files"]:
                env_keys[m.group(1)]["files"].append(str(p))
    browsers = []
    if include_browser:
        for kind, path in _browser_dbs():
            try:
                _scan_text(_read_browser(kind, path), f"{kind}:{path}", found)
                browsers.append({"kind": kind, "path": str(path), "ok": True})
            except Exception as e:
                browsers.append({"kind": kind, "path": str(path), "ok": False, "error": str(e)[:200]})

    # マスターとの突き合わせ
    try:
        master = load_master()
    except Exception:
        master = {"accounts": []}
    known = {}
    for a in master["accounts"]:
        for plat, v in a["platforms"].items():
            h = (v.get("handle") or "").lstrip("@").lower()
            if h:
                known[(plat, h)] = a["internal_key"]
            if v.get("domain"):
                known[("wordpress", v["domain"].lower())] = a["internal_key"]
    # 人が確定済みの候補（accounts_master.candidate_notes）: ignore は落とす（alias_of は正式アカウントに寄せる）、keep は別枠
    notes = master.get("candidate_notes") or {}
    ignored = {(i["platform"], i["value"].lower()): i for i in notes.get("ignore", [])}
    kept = {(k["platform"], k["value"].lower()): k for k in notes.get("keep", [])}
    matches, candidates, resolved = [], [], []
    for plat, vals in found.items():
        for val, srcs in vals.items():
            ig = ignored.get((plat, val.lower())) or kept.get((plat, val.lower()))
            if ig:
                resolved.append({"platform": plat, "value": val, "source_count": len(srcs),
                                 "decision": "keep" if (plat, val.lower()) in kept else "ignore",
                                 "reason": ig.get("reason") or ig.get("memo"), "alias_of": ig.get("alias_of")})
                continue
            key = known.get((plat, val.lower().removeprefix("www."))) or (
                next((k for (pl, h), k in known.items() if h == val.lower()), None) if plat == "mention" else None)
            row = {"platform": plat, "value": val, "sources": sorted(srcs)[:5], "source_count": len(srcs)}
            (matches if key else candidates).append({**row, "account": key} if key else row)
    report = {"generated_at": C.now_iso(), "roots": [str(r) for r in roots_p], "files_scanned": scanned,
              "browser_sources": browsers, "matched_to_master": sorted(matches, key=lambda r: -r["source_count"]),
              "unmatched_candidates": sorted(candidates, key=lambda r: -r["source_count"])[:200],
              "resolved_candidates": resolved,
              "credential_keys": env_keys}
    C.write_json(C.DATA_DIR / "discovery" / "report.json", report)
    return report
