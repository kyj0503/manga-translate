from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Protocol, Sequence

from .glossary import GlossaryEntry, relevant_entries
from .llm.client import ChatResult, LLMError
from .types import TextBlock

PROMPT_VERSION = 1

SYSTEM_PROMPT = """You translate Japanese manga dialogue into natural Korean.
Rules:
- Translate every item in "bubbles" and return exactly one translation per id.
- The bubbles are one page in reading order. Use them and "previous_pages" as context; Japanese often omits the subject.
- Keep each character's speech level (반말/존댓말) consistent with previous pages.
- Write natural spoken Korean, not a literal translation. Keep it short enough to fit in a speech bubble.
- Translate sound effects briefly as Korean onomatopoeia.
- Always use the "glossary" translation for listed terms.
- If a page image is attached, use it only as context (who is speaking, expressions, mood). Translate exactly the given bubbles; do not add text you see in the image.
- Output only the JSON object."""

RESPONSE_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "translations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"id": {"type": "integer"}, "ko": {"type": "string"}},
                "required": ["id", "ko"],
            },
        }
    },
    "required": ["translations"],
}

MAX_ATTEMPTS = 2  # first request + one retry for missing ids or LLM errors

ContextPage = list[tuple[str, str]]


class ChatJsonClient(Protocol):
    def chat_json(
        self,
        messages: list[dict],
        schema: dict,
        *,
        temperature: float = ...,
        extra_body: dict | None = ...,
    ) -> ChatResult: ...


@dataclass(frozen=True)
class PageTranslation:
    translations: dict[int, str]
    failed_ids: tuple[int, ...]
    completion_tokens: int
    tokens_per_second: float | None
    elapsed_s: float


def build_messages(
    blocks: Sequence[TextBlock],
    context_pages: Sequence[ContextPage],
    glossary: Sequence[GlossaryEntry],
    page_image: str | None = None,
) -> list[dict]:
    payload = {
        "glossary": [{"ja": e.ja, "ko": e.ko, "note": e.note} for e in glossary],
        "previous_pages": [[{"ja": ja, "ko": ko} for ja, ko in page] for page in context_pages],
        "bubbles": [{"id": b.id, "ja": b.ja} for b in blocks],
    }
    text = json.dumps(payload, ensure_ascii=False)
    user_content: str | list[dict] = text
    if page_image is not None:
        user_content = [
            {"type": "image_url", "image_url": {"url": page_image}},
            {"type": "text", "text": text},
        ]
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def parse_translations(content: dict, expected_ids: set[int]) -> dict[int, str]:
    result: dict[int, str] = {}
    for item in content.get("translations", []):
        if not isinstance(item, dict):
            continue
        block_id, ko = item.get("id"), item.get("ko")
        if isinstance(block_id, int) and block_id in expected_ids and isinstance(ko, str) and ko.strip():
            result.setdefault(block_id, ko.strip())
    return result


class Translator:
    def __init__(
        self,
        client: ChatJsonClient,
        *,
        temperature: float = 0.3,
        extra_body: dict | None = None,
    ) -> None:
        self._client = client
        self._temperature = temperature
        self._extra_body = extra_body

    def translate_page(
        self,
        blocks: Sequence[TextBlock],
        context_pages: Sequence[ContextPage] = (),
        glossary: Sequence[GlossaryEntry] = (),
        page_image: str | None = None,
    ) -> PageTranslation:
        start = time.perf_counter()
        translations: dict[int, str] = {}
        tokens = 0
        tokens_per_second: float | None = None
        pending = list(blocks)
        relevant = relevant_entries(glossary, [b.ja for b in blocks])

        for _ in range(MAX_ATTEMPTS):
            if not pending:
                break
            try:
                result = self._client.chat_json(
                    build_messages(pending, context_pages, relevant, page_image),
                    RESPONSE_SCHEMA,
                    temperature=self._temperature,
                    extra_body=self._extra_body,
                )
            except LLMError:
                continue
            tokens += result.completion_tokens
            tokens_per_second = result.tokens_per_second or tokens_per_second
            translations.update(parse_translations(result.content, {b.id for b in pending}))
            pending = [b for b in blocks if b.id not in translations]

        return PageTranslation(
            translations=translations,
            failed_ids=tuple(b.id for b in blocks if b.id not in translations),
            completion_tokens=tokens,
            tokens_per_second=tokens_per_second,
            elapsed_s=time.perf_counter() - start,
        )
