from __future__ import annotations

import json
from dataclasses import dataclass

import httpx


class LLMError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChatResult:
    content: dict
    completion_tokens: int
    tokens_per_second: float | None


class ChatClient:
    """OpenAI-compatible chat client for llama-server with schema-constrained JSON output."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        # trust_env=False: never route loopback traffic through a system proxy.
        self._http = httpx.Client(base_url=base_url, timeout=timeout, transport=transport, trust_env=False)

    def chat_json(
        self,
        messages: list[dict],
        schema: dict,
        *,
        temperature: float = 0.3,
        extra_body: dict | None = None,
    ) -> ChatResult:
        body = {
            "model": "local",
            "messages": messages,
            "temperature": temperature,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "result", "strict": True, "schema": schema},
            },
            **(extra_body or {}),
        }
        try:
            response = self._http.post("/v1/chat/completions", json=body)
            response.raise_for_status()
            data = response.json()
            text = data["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            raise LLMError(f"LLM 요청 실패: {e}") from e

        try:
            content = json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"LLM 응답이 JSON이 아닙니다: {text[:200]!r}") from e
        if not isinstance(content, dict):
            raise LLMError(f"LLM 응답이 JSON 객체가 아닙니다: {text[:200]!r}")

        usage = data.get("usage") or {}
        timings = data.get("timings") or {}
        return ChatResult(
            content=content,
            completion_tokens=int(usage.get("completion_tokens", 0)),
            tokens_per_second=timings.get("predicted_per_second"),
        )

    def close(self) -> None:
        self._http.close()
