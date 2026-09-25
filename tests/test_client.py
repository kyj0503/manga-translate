import json

import httpx
import pytest

from manga_viewer.llm.client import ChatClient, LLMError

SCHEMA = {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"]}


def completion(content, tokens=12, tps=40.0):
    return {
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"completion_tokens": tokens},
        "timings": {"predicted_per_second": tps},
    }


def client_with(handler):
    return ChatClient("http://llm.test", transport=httpx.MockTransport(handler))


def test_sends_schema_and_parses_content():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=completion('{"a": 1}'))

    result = client_with(handler).chat_json(
        [{"role": "user", "content": "hi"}],
        SCHEMA,
        temperature=0.2,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )

    assert seen["path"] == "/v1/chat/completions"
    body = seen["body"]
    assert body["temperature"] == 0.2
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"] == SCHEMA
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert result.content == {"a": 1}
    assert result.completion_tokens == 12
    assert result.tokens_per_second == 40.0


def test_http_error_raises_llm_error():
    client = client_with(lambda request: httpx.Response(500, text="oops"))
    with pytest.raises(LLMError):
        client.chat_json([], SCHEMA)


def test_invalid_json_raises_llm_error():
    client = client_with(lambda request: httpx.Response(200, json=completion("not json")))
    with pytest.raises(LLMError, match="JSON"):
        client.chat_json([], SCHEMA)


def test_connection_error_raises_llm_error():
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(LLMError):
        client_with(handler).chat_json([], SCHEMA)
