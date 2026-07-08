"""The only module that imports `anthropic`. Every other module calls through here.

Why centralize this: it means "what does a query cost" has one place to look (usage is
recorded here, right after every response comes back), and it makes tests trivial — tests
monkeypatch `_get_client` instead of mocking the network.
"""

from typing import TypeVar

import anthropic
from pydantic import BaseModel

from finrag.config import settings
from finrag.observability import record_llm_usage

T = TypeVar("T", bound=BaseModel)

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    """Lazy singleton so importing this module doesn't require an API key.

    A module-level function (not a bare module-level client) so tests can monkeypatch
    `finrag.llm._get_client` to return a fake without touching the real SDK.
    """
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def complete(system: str, user: str, model: str | None = None) -> str:
    """Plain text completion. Returns the concatenated text blocks of the response."""
    model = model or settings.answer_model
    client = _get_client()
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    record_llm_usage(model, response.usage.input_tokens, response.usage.output_tokens)
    return "".join(block.text for block in response.content if block.type == "text")


def extract(system: str, user: str, schema: type[T], model: str | None = None) -> T:
    """Structured-output completion: returns a validated instance of `schema`.

    Uses `client.messages.parse()` — the SDK builds the JSON schema from the Pydantic
    model, validates the response against it, and hands back a parsed instance. No
    hand-rolled JSON parsing or repair logic needed.
    """
    model = model or settings.extract_model
    client = _get_client()
    response = client.messages.parse(
        model=model,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_format=schema,
    )
    record_llm_usage(model, response.usage.input_tokens, response.usage.output_tokens)
    return response.parsed_output
