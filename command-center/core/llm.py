"""Claude API の薄いラッパー（構造化出力 + ストリーミング + サーバー側フォールバック）。"""
from __future__ import annotations

import json
from typing import Any

from core import config as C


class LLMError(RuntimeError):
    pass


def _client():
    try:
        import anthropic
    except ImportError as e:
        raise LLMError("anthropic が未インストール。pip install -r requirements.txt") from e
    return anthropic.Anthropic()  # ANTHROPIC_API_KEY / ant auth login のプロファイルを自動解決


def generate_json(system: str, user: str, schema: dict[str, Any], settings: dict | None = None,
                  max_tokens: int | None = None) -> dict[str, Any]:
    import anthropic

    s = (settings or C.load_settings()).get("llm", {})
    model = s.get("model", "claude-opus-5-5")
    kwargs: dict[str, Any] = dict(
        model=model,
        max_tokens=max_tokens or int(s.get("max_tokens", 32000)),
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
        thinking={"type": "adaptive"},
        output_config={"effort": s.get("effort", "high"),
                       "format": {"type": "json_schema", "schema": schema}},
    )
    client = _client()
    try:
        if s.get("use_server_fallback", True):
            with client.beta.messages.stream(betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                                             **kwargs) as stream:
                msg = stream.get_final_message()
        else:
            with client.messages.stream(**kwargs) as stream:
                msg = stream.get_final_message()
    except anthropic.AuthenticationError as e:
        raise LLMError("ANTHROPIC_API_KEY が無効か未設定（config/.env）") from e
    except anthropic.RateLimitError as e:
        raise LLMError("レート制限。少し置いて再実行") from e
    except anthropic.APIStatusError as e:
        raise LLMError(f"API エラー {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise LLMError("Anthropic API に接続できない") from e

    if msg.stop_reason == "refusal":
        cat = getattr(getattr(msg, "stop_details", None), "category", None)
        raise LLMError(f"モデルが生成を拒否（category={cat}）。テーマか素材を見直す")
    if msg.stop_reason == "max_tokens":
        raise LLMError("max_tokens で途切れた。settings.yaml の llm.max_tokens を上げる")
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMError(f"JSON を解釈できない: {text[:200]}") from e
