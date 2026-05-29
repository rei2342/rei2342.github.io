import json
import re
import config


class LLMClient:
    def __init__(self):
        self.backend = config.LLM_BACKEND

    def call(self, prompt: str, system: str = "") -> str:
        if self.backend == "claude":
            return self._call_claude(prompt, system)
        elif self.backend == "openai":
            return self._call_openai(prompt, system)
        else:
            raise ValueError(f"Unknown LLM backend: {self.backend}")

    def call_json(self, prompt: str, system: str = "") -> dict:
        raw = self.call(prompt, system)
        return self._parse_json(raw)

    def _call_claude(self, prompt: str, system: str) -> str:
        import anthropic
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        kwargs = {
            "model": config.CLAUDE_MODEL,
            "max_tokens": config.MAX_TOKENS,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        message = client.messages.create(**kwargs)
        return message.content[0].text

    def _call_openai(self, prompt: str, system: str) -> str:
        from openai import OpenAI
        client = OpenAI(api_key=config.OPENAI_API_KEY)
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=messages,
            max_tokens=config.MAX_TOKENS,
        )
        return response.choices[0].message.content

    def _parse_json(self, text: str) -> dict:
        text = text.strip()
        # Try fenced block (with or without closing fence — handles truncation)
        fenced = re.search(r"```(?:json)?\s*([\s\S]+?)(?:\s*```|$)", text)
        if fenced:
            candidate = fenced.group(1).strip()
            if candidate.startswith(("{", "[")):
                text = candidate
        # If still not clean JSON, find the outermost { } or [ ]
        if not text.startswith(("{", "[")):
            match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
            if match:
                text = match.group(1)
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM returned invalid JSON: {e}\n---\n{text[:500]}")
