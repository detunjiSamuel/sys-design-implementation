"""Hand-rolled tracing: nested spans, JSONL trace files, and cost math.

Design: a single module-level stack of open spans. This only works because the whole
project is synchronous, single-threaded CLI code (no async, no threads) — that's the
simplification that lets us skip contextvars/thread-locals entirely. If this ever grew
concurrent callers, the stack would need to become per-thread/per-task state.

Usage:
    with span("ask", question=q):
        with span("retrieve"):
            ...
        with span("llm.complete", model="claude-opus-4-8"):
            record_llm_usage("claude-opus-4-8", input_tokens=123, output_tokens=45)
    # the outermost span, on exit, writes runs/traces/{ts}_{trace_id}.jsonl and returns a summary
"""

import json
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from finrag.config import settings

_stack: list[dict] = []  # open spans, outermost first
_finished: list[dict] = []  # closed spans belonging to the current trace
_trace_id: str | None = None


@contextmanager
def span(name: str, **attrs):
    """Open a span. The first span opened (empty stack) starts a new trace and, on exit,
    flushes all spans to a JSONL file. Nested spans just record themselves.
    """
    global _trace_id
    is_root = len(_stack) == 0
    if is_root:
        _trace_id = uuid.uuid4().hex[:12]
        _finished.clear()

    record = {
        "trace_id": _trace_id,
        "name": name,
        "attrs": attrs,
        "start": time.monotonic(),
        "usage": None,  # filled in by record_llm_usage if this is an LLM span
    }
    _stack.append(record)
    try:
        yield record
    finally:
        record["latency_ms"] = round((time.monotonic() - record["start"]) * 1000, 2)
        _stack.pop()
        _finished.append(record)

        if is_root:
            summary = _flush_trace()
            record["summary"] = summary


def last_span(name: str) -> dict | None:
    """The most recently finished span with this name, from the most recently completed
    trace (`_finished` is cleared only when the next root span opens, so this stays valid
    right up until the caller's next `ask()`/etc.).

    Convenience for callers that don't hold a reference to a span opened deep inside
    someone else's `with span(...)` block -- e.g. the CLI wants the root "ask" span's
    `summary` (latency/tokens/cost/trace path) and the "generate" span's stashed context
    string, but `pipeline.ask()`'s return type is fixed to just `Answer`.
    """
    for record in reversed(_finished):
        if record["name"] == name:
            return record
    return None


def record_llm_usage(model: str, input_tokens: int, output_tokens: int) -> None:
    """Attach token usage + computed cost to the innermost open span. Call this from
    llm.py right after an Anthropic API response comes back.
    """
    if not _stack:
        return  # called outside any span (e.g. in a unit test) — nothing to attach to
    price_in, price_out = settings.pricing.get(model, (0.0, 0.0))
    cost = (input_tokens * price_in + output_tokens * price_out) / 1_000_000
    _stack[-1]["usage"] = {
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 6),
    }


def _flush_trace() -> dict:
    """Write every span in the just-completed trace to a JSONL file and return a summary
    (total latency, tokens, cost) that callers (the CLI, the eval harness) can print.
    """
    trace_dir = settings.runs_dir / "traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%S")
    path = trace_dir / f"{ts}_{_trace_id}.jsonl"

    # Spans nest, so summing every span's latency would double-count time spent inside
    # children. Wall-clock total is just the root span's latency; it closes last, so it's
    # the last entry appended to _finished.
    total_input_tokens = 0
    total_output_tokens = 0
    total_cost = 0.0

    with path.open("w") as f:
        for rec in _finished:
            line = {k: v for k, v in rec.items() if k != "start"}
            f.write(json.dumps(line) + "\n")
            if rec.get("usage"):
                total_input_tokens += rec["usage"]["input_tokens"]
                total_output_tokens += rec["usage"]["output_tokens"]
                total_cost += rec["usage"]["cost_usd"]

    root_latency_ms = _finished[-1]["latency_ms"] if _finished else 0.0

    return {
        "trace_path": str(path),
        "latency_ms": root_latency_ms,
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "cost_usd": round(total_cost, 6),
    }
