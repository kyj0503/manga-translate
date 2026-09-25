"""Translate a page's text blocks through llama-server's OpenAI-compatible chat API.

A JSON schema with one required key per block makes the server return exactly one
translation for every block, in the same numbering.
"""
from __future__ import annotations

import json
from typing import Sequence

import httpx

from .page import PageResult

CONTEXT_PAGES = 3

SYSTEM_PROMPT = (
    "너는 일본 만화 번역가다. 사용자가 보내는 JSON의 각 값은 한 페이지에 있는 말풍선의 일본어 원문이고, "
    "키는 읽는 순서다. 같은 키에 자연스러운 한국어 구어체 번역을 넣은 JSON만 답하라. "
    "인물 이름은 앞 페이지와 같게 옮기고, 말줄임표와 느낌표 같은 부호는 살린다."
)


class TranslateError(RuntimeError):
    pass


def _numbered(values: Sequence[str]) -> str:
    return json.dumps({str(i + 1): v for i, v in enumerate(values)}, ensure_ascii=False)


def translation_schema(count: int) -> dict:
    keys = [str(i + 1) for i in range(count)]
    return {
        "type": "object",
        "properties": {key: {"type": "string"} for key in keys},
        "required": keys,
        "additionalProperties": False,
    }


def build_messages(texts: Sequence[str], context: Sequence[PageResult]) -> list[dict]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for page in context:
        messages.append({"role": "user", "content": _numbered([b.text for b in page.blocks])})
        messages.append({"role": "assistant", "content": _numbered([b.translation for b in page.blocks])})
    messages.append({"role": "user", "content": _numbered(texts)})
    return messages


def parse_translations(content: str, count: int) -> list[str]:
    try:
        data = json.loads(content)
    except ValueError as e:
        raise TranslateError(f"JSON이 아닌 응답: {content[:200]!r}") from e
    if not isinstance(data, dict):
        raise TranslateError(f"객체가 아닌 응답: {content[:200]!r}")
    translations = []
    for i in range(count):
        value = data.get(str(i + 1))
        if not isinstance(value, str):
            raise TranslateError(f"{i + 1}번 번역이 없습니다: {content[:200]!r}")
        translations.append(value)
    return translations


class Translator:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        timeout: float = 60.0,
        attempts: int = 2,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.attempts = attempts
        self._transport = transport

    def translate(self, texts: Sequence[str], context: Sequence[PageResult] = ()) -> list[str]:
        if not texts:
            return []
        payload = {
            "model": self.model,
            "messages": build_messages(texts, context),
            "temperature": 0.1,
            "max_tokens": 2048,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "translations", "strict": True, "schema": translation_schema(len(texts))},
            },
            "chat_template_kwargs": {"enable_thinking": False},
        }
        last_error: Exception | None = None
        for _ in range(self.attempts):
            try:
                # trust_env=False: never route loopback traffic through a system proxy.
                with httpx.Client(timeout=self.timeout, trust_env=False, transport=self._transport) as client:
                    response = client.post(f"{self.base_url}/v1/chat/completions", json=payload)
                    response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                return parse_translations(content, len(texts))
            except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, TranslateError) as e:
                last_error = e
        raise TranslateError(f"번역에 실패했습니다: {last_error}")
