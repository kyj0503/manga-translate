import json

import httpx
import pytest

from manga_translate.page import Block, PageResult
from manga_translate.translate import (
    TranslateError,
    Translator,
    build_messages,
    parse_translations,
    translation_schema,
)


def reply(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_translation_schema_requires_every_key():
    schema = translation_schema(3)
    assert schema["type"] == "object"
    assert list(schema["properties"]) == ["1", "2", "3"]
    assert schema["required"] == ["1", "2", "3"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["2"] == {"type": "string"}


def test_build_messages_puts_context_pages_before_the_request():
    context = [PageResult((1, 1), (Block((0, 0, 1, 1), False, "前", "앞"),))]
    messages = build_messages(["今", "次"], context)
    assert messages[0]["role"] == "system"
    assert [m["role"] for m in messages[1:]] == ["user", "assistant", "user"]
    assert json.loads(messages[1]["content"]) == {"1": "前"}
    assert json.loads(messages[2]["content"]) == {"1": "앞"}
    assert json.loads(messages[3]["content"]) == {"1": "今", "2": "次"}


def test_parse_translations():
    assert parse_translations('{"2": "나", "1": "가"}', 2) == ["가", "나"]
    with pytest.raises(TranslateError):
        parse_translations('{"1": "가"}', 2)
    with pytest.raises(TranslateError):
        parse_translations('{"1": 3}', 1)
    with pytest.raises(TranslateError):
        parse_translations("not json", 1)
    with pytest.raises(TranslateError):
        parse_translations('["가"]', 1)


def test_translate_sends_schema_and_returns_in_order():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, json.loads(request.content)))
        return reply(json.dumps({"1": "안녕", "2": "엣"}, ensure_ascii=False))

    translator = Translator("http://127.0.0.1:9", "gemma", transport=httpx.MockTransport(handler))
    assert translator.translate(["こんにちは", "えっ"]) == ["안녕", "엣"]

    [(path, body)] = seen
    assert path == "/v1/chat/completions"
    assert body["model"] == "gemma"
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"] == translation_schema(2)
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert json.loads(body["messages"][-1]["content"]) == {"1": "こんにちは", "2": "えっ"}


def test_translate_retries_once_after_a_bad_reply():
    replies = iter([reply('{"1": "가"}'), reply('{"1": "가", "2": "나"}')])
    calls = []

    def handler(request):
        calls.append(1)
        return next(replies)

    translator = Translator("http://127.0.0.1:9", "gemma", transport=httpx.MockTransport(handler))
    assert translator.translate(["a", "b"]) == ["가", "나"]
    assert len(calls) == 2


def test_translate_gives_up_after_two_attempts():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(500, json={"error": "boom"})

    translator = Translator("http://127.0.0.1:9", "gemma", transport=httpx.MockTransport(handler))
    with pytest.raises(TranslateError, match="번역에 실패했습니다"):
        translator.translate(["a"])
    assert len(calls) == 2


def test_translate_nothing_makes_no_request():
    def handler(request):
        raise AssertionError("no request expected")

    translator = Translator("http://127.0.0.1:9", "gemma", transport=httpx.MockTransport(handler))
    assert translator.translate([]) == []
