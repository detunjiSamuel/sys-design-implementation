"""llm.py tests: monkeypatch the client getter with a fake, no network involved."""

from dataclasses import dataclass, field

import pytest
from pydantic import BaseModel

from finrag import llm
from finrag.config import settings
from finrag.observability import span


@dataclass
class FakeUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class FakeMessage:
    content: list
    usage: FakeUsage


@dataclass
class FakeParsedMessage:
    parsed_output: BaseModel
    usage: FakeUsage


class FakeMessages:
    """Stands in for `client.messages` and records what it was called with."""

    def __init__(self, create_return=None, parse_return=None):
        self._create_return = create_return
        self._parse_return = parse_return
        self.create_calls: list[dict] = []
        self.parse_calls: list[dict] = []

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return self._create_return

    def parse(self, **kwargs):
        self.parse_calls.append(kwargs)
        return self._parse_return


@dataclass
class FakeClient:
    messages: FakeMessages = field(default_factory=FakeMessages)


class DummySchema(BaseModel):
    low_level: list[str]
    high_level: list[str]


def test_complete_extracts_text_and_records_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_response = FakeMessage(
        content=[FakeTextBlock(text="Hello, "), FakeTextBlock(text="world.")],
        usage=FakeUsage(input_tokens=12, output_tokens=34),
    )
    fake_client = FakeClient(messages=FakeMessages(create_return=fake_response))
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    with span("test-trace") as root:
        result = llm.complete(system="sys", user="hi", model="claude-opus-4-8")

    assert result == "Hello, world."
    # complete() opens no span of its own; usage attaches to whatever span is open.
    assert root["usage"] == {
        "model": "claude-opus-4-8",
        "input_tokens": 12,
        "output_tokens": 34,
        "cost_usd": round((12 * 5.00 + 34 * 25.00) / 1_000_000, 6),
    }
    assert fake_client.messages.create_calls[0]["model"] == "claude-opus-4-8"


def test_complete_ignores_non_text_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    @dataclass
    class FakeToolUseBlock:
        type: str = "tool_use"

    fake_response = FakeMessage(
        content=[FakeToolUseBlock(), FakeTextBlock(text="only this")],
        usage=FakeUsage(input_tokens=1, output_tokens=1),
    )
    fake_client = FakeClient(messages=FakeMessages(create_return=fake_response))
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    with span("test-trace"):
        result = llm.complete(system="sys", user="hi")

    assert result == "only this"


def test_complete_defaults_to_answer_model(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_response = FakeMessage(content=[FakeTextBlock(text="x")], usage=FakeUsage(1, 1))
    fake_client = FakeClient(messages=FakeMessages(create_return=fake_response))
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    with span("test-trace"):
        llm.complete(system="sys", user="hi")

    assert fake_client.messages.create_calls[0]["model"] == settings.answer_model


def test_extract_returns_parsed_output_and_records_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    parsed = DummySchema(low_level=["Apple"], high_level=["supply chain"])
    fake_response = FakeParsedMessage(parsed_output=parsed, usage=FakeUsage(input_tokens=5, output_tokens=6))
    fake_client = FakeClient(messages=FakeMessages(parse_return=fake_response))
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    with span("test-trace") as root:
        result = llm.extract(system="sys", user="hi", schema=DummySchema, model="claude-opus-4-8")

    assert result == parsed
    assert fake_client.messages.parse_calls[0]["output_format"] is DummySchema
    assert root["usage"]["input_tokens"] == 5
    assert root["usage"]["output_tokens"] == 6
