"""The query pipeline, as a LangGraph `StateGraph`: classify -> retrieve -> generate.

This is the one place LangGraph is used in the whole project (PLAN.md is explicit that
ingestion stays plain scripts — wrapping a linear batch job in a graph framework would add
nothing). The query flow earns it: it is genuinely a small state machine with a real
branch (does this question need classifying, or did the caller already pick a mode?), and
making that branch explicit as a graph is more inspectable than an if/elif ladder.

Flow:

    question, mode ──▶ [conditional entry] ──▶ classify? ──▶ retrieve ──▶ generate ──▶ answer
                              │                    │
                     mode != "auto" ────────▶ skip classify (mode is already decided)

`classify` only ever runs when `mode == "auto"`: it asks the LLM to label the question
local / multi_hop / global and maps that label to a concrete retriever name. `retrieve`
dispatches to the retriever registry (`RETRIEVERS`) by name. `generate` calls
`answer.generate`. Every node is a plain function `State -> dict` (LangGraph merges the
returned dict into state) — no classes, no inheritance, easy to read top to bottom.
"""

from typing import Literal, TypedDict

from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from finrag.answer import generate as generate_answer
from finrag.llm import extract as llm_extract
from finrag.models import Answer, RetrievalResult
from finrag.observability import span
from finrag.retrievers.graph_rag import GraphRAGRetriever
from finrag.retrievers.light_rag import LightRAGRetriever
from finrag.retrievers.naive import NaiveRetriever

# name -> zero-arg factory. Each retriever's constructor defaults every argument to a
# real store, so calling the factory with no args is enough to build a working retriever.
# Exposed so evals/run_evals.py can iterate every mode without importing each class itself.
RETRIEVERS = {
    "naive": NaiveRetriever,
    "graphrag": GraphRAGRetriever,
    "lightrag": LightRAGRetriever,
}

Tier = Literal["local", "multi_hop", "global"]

# local -> naive: one chunk should have the answer, no graph needed.
# multi_hop -> graphrag: answer requires connecting a small number of specific entities.
# global -> lightrag: answer is a theme spanning many entities; needs the thematic index.
TIER_TO_MODE: dict[Tier, str] = {
    "local": "naive",
    "multi_hop": "graphrag",
    "global": "lightrag",
}

CLASSIFY_SYSTEM_PROMPT = """\
Classify a question about SEC 10-K filings into exactly one tier:

- local: answered by a single passage about one company (e.g. "What was NVIDIA's data \
center revenue driver?").
- multi_hop: requires connecting a small number of specific entities across documents \
(e.g. "How does Apple's reliance on TSMC relate to NVIDIA's supply chain risk?").
- global: asks about a theme spanning many entities/companies (e.g. "What macroeconomic \
risks recur across all the filings?").
"""


class _TierLabel(BaseModel):
    """Structured-output schema for the classify node. Local to this module: nothing
    outside the pipeline needs to know a question's tier, only the mode it maps to.
    """

    tier: Tier


class State(TypedDict):
    question: str
    mode: str  # "auto" | "naive" | "graphrag" | "lightrag" -- "auto" is resolved by classify
    tier: str | None  # classify's raw label, or None if classify was skipped/not run yet
    result: RetrievalResult | None
    answer: Answer | None


def _classify(state: State) -> dict:
    """LLM labels the question local/multi_hop/global and that becomes the mode.
    Only reached when mode == "auto" (see `_route_entry`).
    """
    with span("classify"):
        label = llm_extract(
            system=CLASSIFY_SYSTEM_PROMPT,
            user=state["question"],
            schema=_TierLabel,
        )
    return {"tier": label.tier, "mode": TIER_TO_MODE[label.tier]}


def _retrieve(state: State) -> dict:
    """Dispatch to the retriever registry by (by now, always concrete) mode."""
    retriever = RETRIEVERS[state["mode"]]()
    result = retriever.retrieve(state["question"])
    return {"result": result}


def _generate(state: State) -> dict:
    assert state["result"] is not None  # retrieve always runs before generate
    answer = generate_answer(state["question"], state["result"], state["mode"])
    return {"answer": answer}


def _route_entry(state: State) -> str:
    """Conditional entry point: `--mode` explicit means the caller already decided, so
    classify is skipped entirely (and never calls the LLM) and we go straight to retrieve.
    """
    return "classify" if state["mode"] == "auto" else "retrieve"


def build_pipeline():
    """Wire the three nodes into a compiled, runnable graph. Called once; `ask` reuses
    the compiled graph across calls via `_get_pipeline`.
    """
    graph = StateGraph(State)
    graph.add_node("classify", _classify)
    graph.add_node("retrieve", _retrieve)
    graph.add_node("generate", _generate)

    graph.set_conditional_entry_point(
        _route_entry, {"classify": "classify", "retrieve": "retrieve"}
    )
    graph.add_edge("classify", "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)

    return graph.compile()


_pipeline = None


def _get_pipeline():
    # Lazy singleton, same pattern as llm.py/embeddings.py: building the graph is cheap
    # but there's no reason to redo it on every `ask()` call.
    global _pipeline
    if _pipeline is None:
        _pipeline = build_pipeline()
    return _pipeline


def ask(question: str, mode: str = "auto") -> Answer:
    """Run one question through the pipeline end to end. Opens the root observability
    span for the whole request -- retrieve/generate/classify all nest under it, and its
    exit is what flushes runs/traces/{timestamp}_{trace_id}.jsonl.
    """
    with span("ask", question=question, mode=mode):
        pipeline = _get_pipeline()
        final_state = pipeline.invoke(
            {"question": question, "mode": mode, "tier": None, "result": None, "answer": None}
        )
        return final_state["answer"]
