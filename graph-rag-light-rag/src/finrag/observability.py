"""Dual-backend tracing: nested spans, JSONL trace files, cost math -- and, when
configured, a mirror into Langfuse (industry-standard hosted LLM observability: trace UI,
history, cost dashboards -- the tool you'd reach for at work, and worth being able to say
you've used).

Local JSONL is *always* written; Langfuse is an optional add-on layered on top of the same
`span()` calls. Both stay because they solve different problems:
  - local JSONL: tests need to run hermetically (no account, no network), and the CLI /
    eval harness need latency+cost synchronously, right when a span closes -- an API round
    trip to a dashboard is the wrong tool for that.
  - Langfuse (when LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY are set): a hosted UI, trace
    history across runs, and cost dashboards -- genuinely useful, and reading your own span
    JSONL next to what the vendor tool renders is the fastest way to learn what it's
    actually doing for you.

Design: a single module-level stack of open spans (see PLAN.md's note on why a stack is
fine here -- synchronous, single-threaded CLI code, no async/threads). The Langfuse mirror
piggybacks on the same nesting: each `span()` call opens a matching Langfuse span via
`start_as_current_observation`, which is itself a context manager, so nesting is handled by
Python's normal call stack (and OpenTelemetry's context propagation) -- we don't need a
second stack to track it.
"""

import json
import logging
import time
import uuid
from contextlib import contextmanager

from finrag.config import settings

try:
    from langfuse import Langfuse
except ImportError:  # pragma: no cover - langfuse is a normal dependency; this is a belt
    Langfuse = None  # and suspenders for a stripped-down install.

_logger = logging.getLogger(__name__)

_stack: list[dict] = []  # open spans, outermost first
_finished: list[dict] = []  # closed spans belonging to the current trace
_trace_id: str | None = None

_langfuse_client: "Langfuse | None" = None
_langfuse_checked = False  # have we already decided whether Langfuse is configured?


def _get_langfuse_client() -> "Langfuse | None":
    """Lazy singleton, same pattern as `llm._get_client`. Returns None (and does nothing
    else -- no network, no warning) unless both LANGFUSE_PUBLIC_KEY and
    LANGFUSE_SECRET_KEY are set, so importing/using this module with no Langfuse account
    is completely inert. Constructing more than one `Langfuse` client per process trips an
    OpenTelemetry "TracerProvider already set" warning, hence the singleton rather than a
    fresh client per span.
    """
    global _langfuse_client, _langfuse_checked
    if _langfuse_checked:
        return _langfuse_client
    _langfuse_checked = True

    if Langfuse is None or not (settings.langfuse_public_key and settings.langfuse_secret_key):
        _logger.debug("Langfuse keys not configured; tracing to local JSONL only.")
        return None

    try:
        _langfuse_client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
    except Exception:  # noqa: BLE001 - a bad Langfuse config must never break tracing
        _logger.debug("Langfuse client construction failed; tracing to local JSONL only.")
        _langfuse_client = None
    return _langfuse_client


@contextmanager
def span(name: str, **attrs):
    """Open a span. The first span opened (empty stack) starts a new trace and, on exit,
    flushes all spans to a JSONL file (and, if configured, to Langfuse). Nested spans just
    record themselves.
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

    client = _get_langfuse_client()
    lf_cm = client.start_as_current_observation(name=name, as_type="span", metadata=attrs) if client else None
    lf_span = lf_cm.__enter__() if lf_cm else None

    try:
        yield record
    finally:
        record["latency_ms"] = round((time.monotonic() - record["start"]) * 1000, 2)
        _stack.pop()
        _finished.append(record)

        if lf_span is not None:
            lf_span.update(metadata=record["attrs"])  # picks up attrs set after span-open
        if lf_cm is not None:
            lf_cm.__exit__(None, None, None)

        if is_root:
            summary = _flush_trace()
            record["summary"] = summary
            if client is not None:
                try:
                    client.flush()
                except Exception:  # noqa: BLE001 - a flaky network must never crash the CLI
                    _logger.debug("Langfuse flush failed; local JSONL trace still written.")


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

    If Langfuse is configured, the same usage is also recorded as a short-lived child
    "generation" observation (model + usage + cost) nested under the currently open span --
    a plain `span` observation can't carry a model/usage/cost (Langfuse only renders those
    for generation-typed observations), so the LLM call gets its own node in the trace tree.
    """
    if not _stack:
        return  # called outside any span (e.g. in a unit test) — nothing to attach to
    price_in, price_out = settings.pricing.get(model, (0.0, 0.0))
    cost_in = round(input_tokens * price_in / 1_000_000, 6)
    cost_out = round(output_tokens * price_out / 1_000_000, 6)
    _stack[-1]["usage"] = {
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost_in + cost_out, 6),
    }

    client = _get_langfuse_client()
    if client is not None:
        generation = client.start_observation(
            name=f"llm:{model}",
            as_type="generation",
            model=model,
            usage_details={"input": input_tokens, "output": output_tokens, "total": input_tokens + output_tokens},
            cost_details={"input": cost_in, "output": cost_out, "total": round(cost_in + cost_out, 6)},
        )
        generation.end()


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
