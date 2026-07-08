"""Nested spans -> one JSONL file per trace, with cost computed from config.PRICING."""

import json

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
