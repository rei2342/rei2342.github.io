"""LLM 呼び出しの薄いラッパー（構造化 JSON 出力）。

バックエンドは settings.yaml の llm.backends の順に試す。既定:
  claude_cli     … ローカルの Claude Code CLI（`claude -p --output-format json --json-schema`）。
                   ログイン中のサブスク枠で動き、API クレジットを使わない
  anthropic_api  … ANTHROPIC_API_KEY（従量課金）。ストリーミング + サーバー側フォールバック
  openai         … OPENAI_API_KEY があるときだけ（Structured Outputs）
  gemini         … GEMINI_API_KEY / GOOGLE_API_KEY があるときだけ（responseSchema）
鍵が無い・CLI が無いバックエンドは飛ばす。残高不足・認証失敗・レート制限などで失敗したら次へ進む。
モデルが生成を拒否したときは次へ進まず止める（別モデルで押し通さない）。
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from core import config as C

DEFAULT_BACKENDS = ["claude_cli", "anthropic_api", "openai", "gemini"]


class LLMError(RuntimeError):
    pass


class LLMRefusal(LLMError):
    """拒否は別バックエンドに回さない。"""


class BackendUnavailable(LLMError):
    """鍵や実行ファイルが無い。次のバックエンドへ。"""


def _strict_schema(schema: Any) -> Any:
    """OpenAI strict モード用に、全 object に required=全プロパティ を補う（既存スキーマは既にほぼ満たしている）。"""
    if isinstance(schema, dict):
        out = {k: _strict_schema(v) for k, v in schema.items()}
        if out.get("type") == "object" and "properties" in out:
            out["required"] = list(out["properties"].keys())
            out["additionalProperties"] = False
        return out
    if isinstance(schema, list):
        return [_strict_schema(v) for v in schema]
    return schema


def _parse_json(text: str, who: str) -> dict[str, Any]:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    try:
        return json.loads(t)
    except json.JSONDecodeError as e:
        raise LLMError(f"{who}: JSON を解釈できない: {t[:200]}") from e


# ---------------------------------------------------------------- claude_cli
def claude_cli_path(settings: dict | None = None) -> str | None:
    s = (settings or {}).get("llm", {})
    for cand in (s.get("claude_cli_path"), os.environ.get("CLAUDE_CLI_PATH"), shutil.which("claude")):
        if cand and Path(cand).expanduser().exists():
            return str(Path(cand).expanduser())
    home = Path.home()
    pats = [home / ".claude/local/claude", home / ".local/bin/claude",
            # Claude デスクトップアプリ同梱の CLI（バージョン付きフォルダ。新しいものを使う）
            home / "Library/Application Support/Claude/claude-code/*/*/claude.app/Contents/MacOS/claude",
            home / "Library/Application Support/Claude/claude-code-vm/*/claude"]
    for pat in pats:
        hits = sorted(glob.glob(str(pat)), key=lambda p: [int(x) if x.isdigit() else x for x in
                                                         p.replace("/", ".").split(".")])
        if hits:
            return hits[-1]
    return None


def _cli_env() -> dict[str, str]:
    """サブスク（OAuth ログイン）で動かすため、API キーや親セッション用の変数を渡さない。"""
    keep = ("HOME", "USER", "LOGNAME", "PATH", "LANG", "LC_ALL", "TMPDIR", "SHELL", "TERM")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env.setdefault("USER", os.environ.get("LOGNAME") or Path.home().name)  # USER が無いと keychain のログインを引けない
    env.setdefault("LOGNAME", env["USER"])
    env.setdefault("LANG", "ja_JP.UTF-8")
    return env


def _call_claude_cli(system: str, user: str, schema: dict, s: dict, max_tokens: int) -> dict[str, Any]:
    exe = claude_cli_path({"llm": s})
    if not exe:
        raise BackendUnavailable("Claude CLI が見つからない（llm.claude_cli_path か CLAUDE_CLI_PATH で指定可）")
    model = s.get("cli_model") or s.get("model", "claude-opus-5-5")
    cmd = [exe, "-p", "--output-format", "json", "--json-schema", json.dumps(schema, ensure_ascii=False),
           "--system-prompt", system, "--tools", "", "--no-session-persistence", "--strict-mcp-config",
           "--setting-sources", "", "--model", model]
    if s.get("effort"):
        cmd += ["--effort", str(s["effort"])]
    try:
        p = subprocess.run(cmd, input=user, capture_output=True, text=True, env=_cli_env(),
                           cwd=str(C.DATA_DIR if C.DATA_DIR.exists() else Path.home()),
                           timeout=int(s.get("cli_timeout_sec", 900)))
    except subprocess.TimeoutExpired as e:
        raise LLMError("Claude CLI がタイムアウト（llm.cli_timeout_sec）") from e
    out = (p.stdout or "").strip()
    try:
        d = json.loads(out.splitlines()[-1] if out else "{}")
    except json.JSONDecodeError:
        raise LLMError(f"Claude CLI の出力を解釈できない (rc={p.returncode}): {(out or p.stderr)[:300]}")
    if d.get("is_error"):
        msg = str(d.get("result") or d.get("terminal_reason") or p.stderr)[:300]
        if "refus" in msg.lower():
            raise LLMRefusal(f"Claude CLI: モデルが生成を拒否: {msg}")
        raise LLMError(f"Claude CLI エラー: {msg}")
    so = d.get("structured_output")
    if isinstance(so, dict):
        return so
    return _parse_json(d.get("result", ""), "Claude CLI")


# ---------------------------------------------------------------- anthropic_api
def _call_anthropic(system: str, user: str, schema: dict, s: dict, max_tokens: int) -> dict[str, Any]:
    key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("REI_AFFSAKU")
    if not key:
        raise BackendUnavailable("ANTHROPIC_API_KEY が無い")
    try:
        import anthropic
    except ImportError as e:
        raise BackendUnavailable("anthropic が未インストール") from e
    # クラウドセッションでは ANTHROPIC_BASE_URL がセッション用に向いているので、ユーザーキー利用時は公式APIに固定する
    client = anthropic.Anthropic(api_key=key, base_url="https://api.anthropic.com")
    kwargs: dict[str, Any] = dict(
        model=s.get("model", "claude-opus-5-5"), max_tokens=max_tokens,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
        thinking={"type": "adaptive"},
        output_config={"effort": s.get("effort", "high"), "format": {"type": "json_schema", "schema": schema}},
    )
    try:
        if s.get("use_server_fallback", True):
            with client.beta.messages.stream(betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                                             **kwargs) as stream:
                msg = stream.get_final_message()
        else:
            with client.messages.stream(**kwargs) as stream:
                msg = stream.get_final_message()
    except anthropic.AuthenticationError as e:
        raise LLMError("ANTHROPIC_API_KEY が無効") from e
    except anthropic.RateLimitError as e:
        raise LLMError("Anthropic API: レート制限") from e
    except anthropic.APIStatusError as e:
        raise LLMError(f"Anthropic API エラー {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise LLMError("Anthropic API に接続できない") from e
    if msg.stop_reason == "refusal":
        cat = getattr(getattr(msg, "stop_details", None), "category", None)
        raise LLMRefusal(f"モデルが生成を拒否（category={cat}）。テーマか素材を見直す")
    if msg.stop_reason == "max_tokens":
        raise LLMError("max_tokens で途切れた。settings.yaml の llm.max_tokens を上げる")
    return _parse_json("".join(b.text for b in msg.content if getattr(b, "type", "") == "text"), "Anthropic API")


# ---------------------------------------------------------------- openai / gemini
def _call_openai(system: str, user: str, schema: dict, s: dict, max_tokens: int) -> dict[str, Any]:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise BackendUnavailable("OPENAI_API_KEY が無い")
    import requests

    r = requests.post("https://api.openai.com/v1/chat/completions", timeout=600,
                      headers={"Authorization": f"Bearer {key}"},
                      json={"model": s.get("openai_model", "gpt-5"),
                            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                            "max_completion_tokens": max_tokens,
                            "response_format": {"type": "json_schema", "json_schema": {
                                "name": "output", "strict": True, "schema": _strict_schema(schema)}}})
    if r.status_code != 200:
        raise LLMError(f"OpenAI API エラー {r.status_code}: {r.text[:200]}")
    ch = r.json()["choices"][0]
    if ch["message"].get("refusal"):
        raise LLMRefusal(f"OpenAI: 生成を拒否: {ch['message']['refusal'][:200]}")
    return _parse_json(ch["message"].get("content", ""), "OpenAI")


def _gemini_schema(schema: Any) -> Any:
    if isinstance(schema, dict):
        return {k: _gemini_schema(v) for k, v in schema.items() if k != "additionalProperties"}
    if isinstance(schema, list):
        return [_gemini_schema(v) for v in schema]
    return schema


def _call_gemini(system: str, user: str, schema: dict, s: dict, max_tokens: int) -> dict[str, Any]:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise BackendUnavailable("GEMINI_API_KEY が無い")
    import requests

    model = s.get("gemini_model", "gemini-2.5-pro")
    r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                      headers={"x-goog-api-key": key}, timeout=600,
                      json={"systemInstruction": {"parts": [{"text": system}]},
                            "contents": [{"role": "user", "parts": [{"text": user}]}],
                            "generationConfig": {"maxOutputTokens": max_tokens, "responseMimeType": "application/json",
                                                 "responseSchema": _gemini_schema(schema)}})
    if r.status_code != 200:
        raise LLMError(f"Gemini API エラー {r.status_code}: {r.text[:200]}")
    cands = r.json().get("candidates") or []
    if not cands or cands[0].get("finishReason") in ("SAFETY", "PROHIBITED_CONTENT"):
        raise LLMRefusal("Gemini: 生成を拒否")
    return _parse_json("".join(p.get("text", "") for p in cands[0]["content"]["parts"]), "Gemini")


BACKENDS = {"claude_cli": _call_claude_cli, "anthropic_api": _call_anthropic,
            "openai": _call_openai, "gemini": _call_gemini}
last_backend: str | None = None  # 直近に成功したバックエンド（下書きに記録する）


def available() -> bool:
    """どれか1つでも使えるバックエンドがあるか（クロールのトーン要約を走らせるかの判定用）。"""
    s = C.load_settings().get("llm", {})
    order = s.get("backends") or DEFAULT_BACKENDS
    return any((b == "claude_cli" and claude_cli_path({"llm": s})) or
               (b == "anthropic_api" and (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("REI_AFFSAKU"))) or
               (b == "openai" and os.environ.get("OPENAI_API_KEY")) or
               (b == "gemini" and (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")))
               for b in order)


def generate_json(system: str, user: str, schema: dict[str, Any], settings: dict | None = None,
                  max_tokens: int | None = None) -> dict[str, Any]:
    global last_backend
    s = (settings or C.load_settings()).get("llm", {})
    mt = max_tokens or int(s.get("max_tokens", 32000))
    errors = []
    for name in s.get("backends") or DEFAULT_BACKENDS:
        fn = BACKENDS.get(name)
        if not fn:
            continue
        try:
            out = fn(system, user, schema, s, mt)
            last_backend = name
            return out
        except LLMRefusal:
            raise
        except BackendUnavailable as e:
            errors.append(f"{name}: スキップ（{e}）")
        except LLMError as e:
            errors.append(f"{name}: {e}")
    raise LLMError("全バックエンドで失敗 → " + " / ".join(errors))
