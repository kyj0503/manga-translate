import json

from manga_viewer.glossary import GlossaryEntry
from manga_viewer.llm.client import ChatResult, LLMError
from manga_viewer.translate import (
    RESPONSE_SCHEMA,
    Translator,
    build_messages,
    parse_translations,
)
from manga_viewer.types import TextBlock


def blk(i, ja):
    return TextBlock(id=i, box=(0, 0, 10, 10), vertical=True, ja=ja)


class FakeClient:
    """Returns queued results (or raises queued exceptions) and records requests."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def chat_json(self, messages, schema, *, temperature=0.3, extra_body=None):
        self.calls.append({"messages": messages, "schema": schema, "extra_body": extra_body})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return ChatResult(content=item, completion_tokens=10, tokens_per_second=35.0)

    def payload(self, call_index):
        content = self.calls[call_index]["messages"][1]["content"]
        if isinstance(content, list):  # image + text parts
            content = next(p["text"] for p in content if p["type"] == "text")
        return json.loads(content)


def test_build_messages_payload_keeps_japanese():
    messages = build_messages(
        [blk(0, "行くぞ")],
        [[("はい", "응")]],
        [GlossaryEntry("悟", "사토루", "주인공")],
    )
    assert messages[0]["role"] == "system"
    assert "行くぞ" in messages[1]["content"]  # ensure_ascii=False
    payload = json.loads(messages[1]["content"])
    assert payload == {
        "glossary": [{"ja": "悟", "ko": "사토루", "note": "주인공"}],
        "previous_pages": [[{"ja": "はい", "ko": "응"}]],
        "bubbles": [{"id": 0, "ja": "行くぞ"}],
    }


def test_parse_translations_ignores_bad_items():
    content = {
        "translations": [
            {"id": 0, "ko": " 가자 "},
            {"id": 0, "ko": "중복"},
            {"id": 9, "ko": "없는 id"},
            {"id": 1, "ko": ""},
            {"id": "2", "ko": "문자열 id"},
            "garbage",
        ]
    }
    assert parse_translations(content, {0, 1, 2}) == {0: "가자"}


def test_translates_all_in_one_call():
    client = FakeClient({"translations": [{"id": 0, "ko": "가자"}, {"id": 1, "ko": "응"}]})
    result = Translator(client).translate_page([blk(0, "行くぞ"), blk(1, "うん")])
    assert result.translations == {0: "가자", 1: "응"}
    assert result.failed_ids == ()
    assert len(client.calls) == 1
    assert client.calls[0]["schema"] == RESPONSE_SCHEMA
    assert result.completion_tokens == 10
    assert result.tokens_per_second == 35.0


def test_missing_ids_are_retried_once_with_only_missing_bubbles():
    client = FakeClient(
        {"translations": [{"id": 0, "ko": "가자"}]},
        {"translations": [{"id": 1, "ko": "응"}]},
    )
    result = Translator(client).translate_page([blk(0, "行くぞ"), blk(1, "うん")])
    assert result.translations == {0: "가자", 1: "응"}
    assert client.payload(1)["bubbles"] == [{"id": 1, "ja": "うん"}]
    assert result.completion_tokens == 20


def test_still_missing_after_retry_is_reported():
    client = FakeClient(
        {"translations": [{"id": 0, "ko": "가자"}]},
        {"translations": []},
    )
    result = Translator(client).translate_page([blk(0, "行くぞ"), blk(1, "うん")])
    assert result.translations == {0: "가자"}
    assert result.failed_ids == (1,)


def test_llm_error_is_retried_once():
    client = FakeClient(LLMError("down"), {"translations": [{"id": 0, "ko": "가자"}]})
    result = Translator(client).translate_page([blk(0, "行くぞ")])
    assert result.translations == {0: "가자"}


def test_two_llm_errors_fail_every_bubble():
    client = FakeClient(LLMError("down"), LLMError("down"))
    result = Translator(client).translate_page([blk(0, "行くぞ"), blk(1, "うん")])
    assert result.translations == {}
    assert result.failed_ids == (0, 1)


def test_empty_page_makes_no_call():
    client = FakeClient()
    result = Translator(client).translate_page([])
    assert result.translations == {}
    assert client.calls == []


def test_only_relevant_glossary_and_extra_body_are_sent():
    client = FakeClient({"translations": [{"id": 0, "ko": "사토루, 가자"}]})
    translator = Translator(client, extra_body={"chat_template_kwargs": {"enable_thinking": False}})
    translator.translate_page(
        [blk(0, "悟、行くぞ")],
        glossary=[GlossaryEntry("悟", "사토루"), GlossaryEntry("呪術", "주술")],
    )
    assert client.payload(0)["glossary"] == [{"ja": "悟", "ko": "사토루", "note": ""}]
    assert client.calls[0]["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}


def test_build_messages_with_page_image():
    messages = build_messages([blk(0, "行くぞ")], [], [], page_image="data:image/jpeg;base64,AAAA")
    parts = messages[1]["content"]
    assert parts[0] == {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,AAAA"}}
    assert parts[1]["type"] == "text"
    assert json.loads(parts[1]["text"])["bubbles"] == [{"id": 0, "ja": "行くぞ"}]


def test_page_image_is_sent_on_retry_too():
    client = FakeClient(
        {"translations": [{"id": 0, "ko": "가자"}]},
        {"translations": [{"id": 1, "ko": "응"}]},
    )
    Translator(client).translate_page([blk(0, "行くぞ"), blk(1, "うん")], page_image="data:image/jpeg;base64,AAAA")
    for call in client.calls:
        assert call["messages"][1]["content"][0]["type"] == "image_url"
