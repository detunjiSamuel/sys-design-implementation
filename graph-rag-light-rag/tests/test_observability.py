"""Nested spans -> one JSONL file per trace, with cost computed from config.PRICING.

Also covers the optional Langfuse mirror: inert with no keys configured (no client ever
constructed, no network), and -- with fake keys -- mirroring root/child spans and LLM
usage into a recording fake that stands in for the real `Langfuse` client (no test here
ever talks to the real SDK's network path).
"""

import json

import pytest

import finrag.observability as observability
from finrag.config import settings
from finrag.observability import record_llm_usage, span


def test_nested_spans_write_one_jsonl_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "runs_dir", tmp_path)

    with span("ask", question="what?"):
        with span("retrieve"):
            pass
        with span("llm.complete", model="claude-opus-4-8"):
            record_llm_usage("claude-opus-4-8", input_tokens=1000, output_tokens=200)

    trace_files = list((tmp_path / "traces").glob("*.jsonl"))
    assert len(trace_files) == 1

    lines = [json.loads(line) for line in trace_files[0].read_text().splitlines()]
    # retrieve, llm.complete, ask (closed in that order: innermost first, root last)
    assert [line["name"] for line in lines] == ["retrieve", "llm.complete", "ask"]
    assert all("trace_id" in line for line in lines)
    assert len({line["trace_id"] for line in lines}) == 1  # all spans share one trace


def test_cost_math_is_correct(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "runs_dir", tmp_path)

    with span("ask"):
        with span("llm.extract", model="claude-opus-4-8") as s:
            record_llm_usage("claude-opus-4-8", input_tokens=1_000_000, output_tokens=1_000_000)

    price_in, price_out = settings.pricing["claude-opus-4-8"]
    expected_cost = price_in + price_out  # 1M in + 1M out tokens, priced per-million
    assert s["usage"]["cost_usd"] == expected_cost


def test_trace_summary_aggregates_usage(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "runs_dir", tmp_path)

    with span("ask") as root:
        with span("llm.a", model="claude-haiku-4-5"):
            record_llm_usage("claude-haiku-4-5", input_tokens=100, output_tokens=50)
        with span("llm.b", model="claude-haiku-4-5"):
            record_llm_usage("claude-haiku-4-5", input_tokens=200, output_tokens=25)

    summary = root["summary"]
    assert summary["input_tokens"] == 300
    assert summary["output_tokens"] == 75
    price_in, price_out = settings.pricing["claude-haiku-4-5"]
    expected_cost = round((300 * price_in + 75 * price_out) / 1_000_000, 6)
    assert summary["cost_usd"] == expected_cost
    assert summary["latency_ms"] >= 0


def test_record_llm_usage_outside_span_is_a_noop() -> None:
    # Should not raise even though no span is open.
    record_llm_usage("claude-opus-4-8", input_tokens=10, output_tokens=10)


# --- Langfuse mirror ------------------------------------------------------------------
#
# `observability._get_langfuse_client()` caches its decision (constructed client, or
# "not configured") for the life of the process -- reset that cache before every test
# here so tests don't leak into each other regardless of order.


@pytest.fixture(autouse=True)
def _reset_langfuse_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(observability, "_langfuse_client", None)
    monkeypatch.setattr(observability, "_langfuse_checked", False)


def test_no_langfuse_keys_means_no_client_is_constructed(monkeypatch: pytest.MonkeyPatch) -> None:
    # settings.langfuse_public_key / _secret_key default to "" -- nothing in conftest.py
    # sets them, matching a real environment with no Langfuse account.
    construct_calls: list[dict] = []

    class SpyLangfuse:
        def __init__(self, **kwargs):
            construct_calls.append(kwargs)

    monkeypatch.setattr(observability, "Langfuse", SpyLangfuse)

    with span("ask"):
        with span("retrieve"):
            pass
        record_llm_usage("claude-opus-4-8", input_tokens=1, output_tokens=1)

    assert construct_calls == []
    assert observability._get_langfuse_client() is None


class _FakeLangfuseObservation:
    """Records what it was created/updated/ended with. Stands in for the real SDK's
    LangfuseSpan / LangfuseGeneration objects.
    """

    def __init__(self, name, as_type, parent, metadata=None, model=None, usage_details=None, cost_details=None):
        self.name = name
        self.as_type = as_type
        self.parent = parent
        self.metadata = metadata
        self.model = model
        self.usage_details = usage_details
        self.cost_details = cost_details
        self.ended = False

    def update(self, *, metadata=None, **_kwargs) -> None:
        if metadata is not None:
            self.metadata = metadata

    def end(self, **_kwargs) -> None:
        self.ended = True


class _FakeLangfuseSpanContext:
    """What `start_as_current_observation` returns: a context manager whose __enter__
    both returns the observation and pushes it as "current" so children nest under it.
    """

    def __init__(self, client: "FakeLangfuseClient", observation: _FakeLangfuseObservation):
        self._client = client
        self._observation = observation

    def __enter__(self) -> _FakeLangfuseObservation:
        self._client._current_stack.append(self._observation)
        return self._observation

    def __exit__(self, *exc_info) -> bool:
        self._client._current_stack.pop()
        self._observation.ended = True
        return False


class FakeLangfuseClient:
    """A recording fake for the real `langfuse.Langfuse` client -- no network, ever.
    Mirrors just the slice of the real API `observability.py` calls: `start_as_current_
    observation`, `start_observation`, and `flush`.
    """

    def __init__(self, *, public_key: str, secret_key: str, host: str):
        self.public_key = public_key
        self.secret_key = secret_key
        self.host = host
        self.observations: list[_FakeLangfuseObservation] = []
        self._current_stack: list[_FakeLangfuseObservation] = []
        self.flush_called = False

    def start_as_current_observation(self, *, name, as_type="span", metadata=None, **_kwargs):
        parent = self._current_stack[-1] if self._current_stack else None
        obs = _FakeLangfuseObservation(name, as_type, parent, metadata=metadata)
        self.observations.append(obs)
        return _FakeLangfuseSpanContext(self, obs)

    def start_observation(
        self, *, name, as_type="span", model=None, usage_details=None, cost_details=None, **_kwargs
    ):
        parent = self._current_stack[-1] if self._current_stack else None
        obs = _FakeLangfuseObservation(
            name, as_type, parent, model=model, usage_details=usage_details, cost_details=cost_details
        )
        self.observations.append(obs)
        return obs

    def flush(self) -> None:
        self.flush_called = True


def test_langfuse_mirrors_spans_and_llm_usage_when_keys_are_set(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "runs_dir", tmp_path)
    monkeypatch.setattr(settings, "langfuse_public_key", "pk-test")
    monkeypatch.setattr(settings, "langfuse_secret_key", "sk-test")

    constructed: dict[str, FakeLangfuseClient] = {}

    def fake_ctor(**kwargs):
        client = FakeLangfuseClient(**kwargs)
        constructed["client"] = client
        return client

    monkeypatch.setattr(observability, "Langfuse", fake_ctor)

    with span("ask", question="what?"):
        with span("retrieve"):
            pass
        record_llm_usage("claude-opus-4-8", input_tokens=1000, output_tokens=200)

    client = constructed["client"]
    assert client.public_key == "pk-test"
    assert [o.name for o in client.observations] == ["ask", "retrieve", "llm:claude-opus-4-8"]

    root, retrieve, generation = client.observations
    assert root.parent is None  # root span -> the trace
    assert retrieve.parent is root  # nested span -> child span
    assert generation.parent is root  # LLM usage -> a generation nested under the open span

    assert generation.as_type == "generation"
    assert generation.model == "claude-opus-4-8"
    assert generation.usage_details == {"input": 1000, "output": 200, "total": 1200}
    price_in, price_out = settings.pricing["claude-opus-4-8"]
    expected_cost = round((1000 * price_in + 200 * price_out) / 1_000_000, 6)
    assert generation.cost_details["total"] == expected_cost

    assert client.flush_called is True  # flushed once, at root span exit
    # the local JSONL fallback still wrote its file, same as with no Langfuse configured.
    assert len(list((tmp_path / "traces").glob("*.jsonl"))) == 1
