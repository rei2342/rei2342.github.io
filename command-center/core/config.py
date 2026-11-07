"""パス・設定・認証情報の読み込み。アカウント固有値はここに書かない。"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
MASTER_PATH = CONFIG_DIR / "accounts_master.json"
SETTINGS_PATH = CONFIG_DIR / "settings.yaml"
ENV_PATH = CONFIG_DIR / ".env"
JST = timezone(timedelta(hours=9))

try:
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH, override=False)
except ImportError:  # python-dotenv が無くても環境変数は使える
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def data_path(*parts: str) -> Path:
    p = DATA_DIR.joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_settings() -> dict[str, Any]:
    with open(SETTINGS_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_settings(settings: dict[str, Any]) -> None:
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(settings, f, allow_unicode=True, sort_keys=False)


def is_dry_run(settings: dict | None = None) -> bool:
    if os.environ.get("CC_LIVE") == "1":
        return False
    s = settings or load_settings()
    return bool(s.get("mode", {}).get("dry_run", True))


def env_suffix(internal_key: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", internal_key).strip("_").upper()


def cred(base: str, internal_key: str, settings: dict | None = None) -> str:
    """アカウント別キー → (フォールバック対象アカウントのみ) 素のキー の順に引く。"""
    v = os.environ.get(f"{base}__{env_suffix(internal_key)}", "").strip()
    if v:
        return v
    if base == "THREADS_ACCESS_TOKEN":
        t = _threads_accounts_token(internal_key)
        if t:
            return t
    s = settings or load_settings()
    if s.get("credentials", {}).get("global_fallback_account") == internal_key:
        return os.environ.get(base, "").strip()
    return ""


def _threads_accounts_token(internal_key: str) -> str:
    """既存 Secret THREADS_ACCOUNTS（[{"name":"さくら","token":"..."}]）をラベル/キーで引く。"""
    raw = os.environ.get("THREADS_ACCOUNTS", "").strip()
    if not raw:
        return ""
    try:
        rows = json.loads(raw)
        label = next((a.get("label") for a in (read_json(MASTER_PATH, {}) or {}).get("accounts", [])
                      if a.get("internal_key") == internal_key), None)
        for r in rows:
            if r.get("token") and r.get("name") in (label, internal_key):
                return r["token"].strip()
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass
    return ""


# 媒体ごとに必要な認証キー
CRED_KEYS: dict[str, list[str]] = {
    "wordpress": ["WP_USER", "WP_APP_PASSWORD"],
    "note": ["NOTE_EMAIL", "NOTE_PASSWORD"],  # storage_state があれば不要
    "x": ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"],
    "threads": ["THREADS_ACCESS_TOKEN", "THREADS_USER_ID"],
    "instagram": ["IG_ACCESS_TOKEN", "IG_USER_ID"],
}
OPTIONAL_KEYS = {"x": ["X_BEARER_TOKEN"], "threads": [], "instagram": []}


def has_creds(platform: str, internal_key: str, settings: dict | None = None) -> bool:
    if platform == "note":
        state = DATA_DIR / "sessions" / f"note_{internal_key}.json"
        if state.exists():
            return True
    if platform == "threads":
        # THREADS_USER_ID は "me" で代替できる
        return bool(cred("THREADS_ACCESS_TOKEN", internal_key, settings))
    return all(cred(k, internal_key, settings) for k in CRED_KEYS.get(platform, []))


def read_json(path: Path, default: Any = None) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def append_jsonl(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out


def chromium_executable() -> str | None:
    """Playwright が同梱版を見つけられない環境向け（CHROMIUM_PATH → /opt/pw-browsers の順）。"""
    import glob

    if os.environ.get("CHROMIUM_PATH"):
        return os.environ["CHROMIUM_PATH"]
    hits = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome"))
    return hits[-1] if hits else None


def launch_chromium(pw, headless: bool = True):
    try:
        return pw.chromium.launch(headless=headless)
    except Exception:
        exe = chromium_executable()
        if not exe:
            raise
        return pw.chromium.launch(headless=headless, executable_path=exe)
