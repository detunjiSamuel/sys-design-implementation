"""Typer CLI entry point (`finrag`). Each command is a thin wrapper around a module
function — the CLI itself contains no logic, so every command is also testable/callable
directly from Python.
"""

import sys
from pathlib import Path

import typer

from finrag import index as index_module
from finrag import pipeline
from finrag.extract import build_graph as build_graph_into
from finrag.extract import extract_all
from finrag.ingest.chunk import chunk_all, load_chunks
from finrag.ingest.download import download_all
from finrag.observability import last_span
from finrag.stores.graph_store import Neo4jGraphStore

# evals/ lives at the repo root, a sibling of src/, not inside the finrag package (it's a
# gold-question set + report script, not library code — see PLAN.md's repo layout). Make
# sure the repo root is importable before reaching for it, since `finrag` is an installed
# console script that may run from any cwd.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

app = typer.Typer(help="FinGraphRAG: naive vs GraphRAG vs LightRAG over SEC 10-K filings.")


@app.command()
def download(
    tickers: str = typer.Option(
        None, "--tickers", help="Comma-separated tickers, e.g. AAPL,MSFT. Defaults to config.tickers."
    ),
) -> None:
    """Phase 1: fetch the latest 10-K Items 1/1A/7 for each ticker into data/raw/."""
    ticker_list = [t.strip().upper() for t in tickers.split(",")] if tickers else None
    download_all(ticker_list)


@app.command()
def chunk() -> None:
    """Phase 1: split data/raw/*.txt into data/chunks.jsonl."""
    chunk_all()


@app.command()
def index() -> None:
    """Phase 2: embed data/chunks.jsonl into Chroma's "chunks" collection."""
    count = index_module.index_chunks()
    print(f"indexed {count} chunks into Chroma 'chunks'")


@app.command()
def extract() -> None:
    """Phase 3: LLM entity/relation extraction, checkpointed to data/extractions.jsonl."""
    chunks = load_chunks()
    extract_all(chunks)


@app.command(name="build-graph")
def build_graph() -> None:
    """Phase 3: upsert extractions into Neo4j, then embed entities/relations into Chroma
    so graphrag/lightrag can vector-search them.
    """
    store = Neo4jGraphStore()
    store.ensure_constraints()
    build_graph_into(store)
    n_entities, n_relations = index_module.index_graph()
    print(
        f"build-graph: upserted extractions into Neo4j; "
        f"embedded {n_entities} entities and {n_relations} relations into Chroma"
    )


@app.command()
def ask(
    question: str = typer.Argument(..., help="The question to ask."),
    mode: str = typer.Option(
        "auto", "--mode", help="Retrieval strategy: auto, naive, graphrag, or lightrag."
    ),
    show_context: bool = typer.Option(
        False, "--show-context", help="Print the exact context the model was given."
    ),
) -> None:
    """Phase 5: run a question through the classify -> retrieve -> generate pipeline."""
    valid_modes = {"auto", *pipeline.RETRIEVERS}
    if mode not in valid_modes:
        print(f"unknown --mode {mode!r}; choose from {', '.join(sorted(valid_modes))}")
        raise typer.Exit(code=1)

    answer = pipeline.ask(question, mode=mode)

    print(answer.text)
    if answer.citations:
        print(f"\ncitations: {', '.join(answer.citations)}")

    if show_context:
        generate_span = last_span("generate")
        context = generate_span["attrs"].get("context") if generate_span else None
        print("\n--- context the model saw ---")
        print(context or "(no context recorded)")

    # `pipeline.ask()` only returns an Answer (see PLAN.md's module contract), so the
    # trace summary (attached to the root "ask" span when it closed) is pulled back out
    # via observability.last_span rather than widening ask()'s return type.
    root = last_span("ask")
    summary = root.get("summary", {}) if root else {}
    latency_s = summary.get("latency_ms", 0.0) / 1000
    tokens = summary.get("input_tokens", 0) + summary.get("output_tokens", 0)
    cost = summary.get("cost_usd", 0.0)
    trace_path = summary.get("trace_path", "")
    print(
        f"\nmode={answer.mode} latency={latency_s:.1f}s tokens={tokens / 1000:.1f}k "
        f"cost=${cost:.4f} trace={trace_path}"
    )


@app.command(name="eval")
def eval_cmd(
    modes: str = typer.Option(
        "naive,graphrag,lightrag", "--modes", help="Comma-separated retrieval modes to evaluate."
    ),
    questions: str = typer.Option(
        None, "--questions", help="Path to questions YAML (defaults to evals/questions.yaml)."
    ),
    out: str = typer.Option(
        None, "--out", help="Path to write the results report (defaults to evals/results.md)."
    ),
) -> None:
    """Phase 6: run every question x every mode through the pipeline, LLM-judge each
    answer against its gold reference, and write evals/results.md.
    """
    from evals.run_evals import DEFAULT_QUESTIONS_PATH, DEFAULT_RESULTS_PATH, run_evals

    mode_list = tuple(m.strip() for m in modes.split(",") if m.strip())
    run_evals(
        modes=mode_list,
        questions_path=questions or DEFAULT_QUESTIONS_PATH,
        out_path=out or DEFAULT_RESULTS_PATH,
    )


if __name__ == "__main__":
    app()
