# FinGraphRAG

A comparative RAG lab: **naive vector RAG vs GraphRAG vs LightRAG** over SEC 10-K annual
reports for six companies across sectors (AAPL, MSFT, NVDA, JPM, XOM, PFE). Same
questions, same underlying filings, three retrieval strategies behind one interface — with
an eval harness that measures which strategy wins on which class of question, and why.

The full design log — every decision, why it was made, what was rejected — lives in
[PLAN.md](PLAN.md). This README is the fast path: what it is, how to run it, what it found.

## Why graphs

Naive RAG chunks documents, embeds them, and at query time fetches the chunks most
similar to the question. That works great for "what does Apple say about supply chain
risk" — one chunk *is* the answer. It falls apart on "what risks do Apple and JPMorgan
share" — no single chunk is about both companies, so the similarity mass never lands on
the right passages, and the model either hallucinates a connection or refuses to answer.
GraphRAG fixes this by pre-computing the connections at ingest time: an LLM extracts
entities and relationships into a knowledge graph, so at query time you traverse structure
instead of hoping vector similarity gets lucky. LightRAG keeps that power but drops
Microsoft GraphRAG's expensive community-summarization step — it indexes relationship
*descriptions* directly, so the thematic index is a byproduct of extraction, not a separate
clustering job, and incremental updates are just "extract the new doc, merge nodes."

## Architecture

```
INGEST (offline, run once)
  EDGAR ──download──▶ raw text ──chunk──▶ chunks.jsonl
      chunks ──embed──▶ Chroma "chunks"                        (naive RAG index)
      chunks ──LLM extract──▶ entities + relations
          entities ──▶ Neo4j nodes      + Chroma "entities"    (graph + low-level index)
          relations ──▶ Neo4j edges     + Chroma "relations"   (graph + high-level index)

QUERY (online, per question)                 ┌─ naive:    Chroma chunks top-k
  question ─▶ [classify] ─▶ [retrieve] ──────┼─ graphrag: link entities → k-hop Cypher → chunks
                                             └─ lightrag: LLM keywords → dual-level lookup → merge
              [generate] ─▶ answer + citations + trace (latency, tokens, $)
```

Chroma (embedded vector store, 3 collections: `chunks`, `entities`, `relations`) and Neo4j
(graph store, via `docker-compose`) are the only two stores. Every LLM call goes through
`llm.py`, the only file in the project that imports `anthropic`. Every retrieval strategy
implements the same 5-line `Retriever` protocol, so naive/graphrag/lightrag are swappable
behind `pipeline.ask(question, mode=...)`.

### Repo layout

```
src/finrag/
├── config.py          # every knob: models, Neo4j, chunking, top-k, pricing table
├── models.py           # Chunk, Entity, Relation, RetrievalResult, Answer, ...
├── llm.py               # the only file that talks to the Anthropic API
├── embeddings.py         # the only file that computes embeddings (FastEmbed, local)
├── observability.py       # span() context manager, JSONL traces, cost math
├── ingest/                # download.py (EDGAR), chunk.py (splitter)
├── extract.py              # chunks -> entities/relations via LLM structured output
├── stores/                  # vector_store.py (Chroma), graph_store.py (Neo4j + fake)
├── retrievers/                # naive.py, graph_rag.py, light_rag.py
├── pipeline.py                 # LangGraph: classify -> retrieve -> generate
├── answer.py                    # prompt assembly + citation-grounded generation
└── cli.py                        # typer: download, chunk, index, extract, build-graph, ask, eval
evals/
├── questions.yaml                # 24 gold questions, 3 tiers (see "The comparison" below)
└── run_evals.py                   # runs every question x every mode, LLM-judges, writes results.md
tests/                              # offline unit tests: FakeLLM, FakeGraphStore, no network
```

See [PLAN.md](PLAN.md) for the full architect's log — the table of every design decision
and what was rejected, the Neo4j graph schema, and the module contracts each file exposes.

## Quickstart

```bash
cp .env.example .env            # add ANTHROPIC_API_KEY
docker compose up -d            # Neo4j on localhost:7474 (browser) / :7687 (bolt)
pip install -e ".[dev]"
finrag download && finrag chunk # Phase 1: ~5 min, no LLM cost
finrag index                    # Phase 2: local embeddings (FastEmbed, CPU), free
finrag extract                  # Phase 3: the LLM-cost step (~$2-10 depending on model)
finrag build-graph
finrag ask "What risks do Apple and JPMorgan share?" --mode naive     # watch it fail
finrag ask "What risks do Apple and JPMorgan share?" --mode lightrag  # watch it work
python evals/run_evals.py       # the comparison table
pytest                          # offline, always green
```

Everything except `extract`, `ask`, and `eval` runs with **no API key** — download,
chunk, and index are pure data-wrangling plus local embeddings. `extract` is the one step
that costs real money: it calls the LLM once per chunk (roughly 300-600 chunks across six
10-Ks), so expect low single-digit dollars on a cheaper model and up to ~$10 on a larger
one; `config.py`'s `pricing` table is what `finrag extract` sums against at the end of the
run so you see the actual number, not an estimate. `ask` and `eval` each cost a handful of
LLM calls per query (one for generation, plus a keyword-extraction call for `lightrag` and
a classification call for `--mode auto`; `eval` additionally pays for one judge call per
question x mode).

## The comparison

`evals/questions.yaml` has 24 questions in three tiers, each tier a hypothesis about where
graph retrieval should help:

- **local** (8 questions) — answerable from a single chunk of a single filing, e.g. "What
  was NVIDIA's data center revenue driver?" Hypothesis: all three modes tie, so naive wins
  on cost — there's no multi-hop structure to exploit.
- **multi_hop** (8 questions) — connects 2-3 specific entities/companies, e.g. "How does
  TSMC dependence connect Apple's and NVIDIA's supply chain risk?" Hypothesis: graphrag and
  lightrag win because the graph pre-computed the TSMC-Apple-NVIDIA connection at ingest
  time; naive has to get lucky that one chunk mentions all three.
- **global** (8 questions) — a theme spanning most/all six companies, e.g. "What
  macroeconomic risks recur across all six filings?" Hypothesis: lightrag's high-level
  (relationship-description) index wins here specifically, since this is the case it was
  built for.

Each question's `gold` field is a **draft** reference answer — see the header comment in
`questions.yaml` for why, and what needs to happen before the eval numbers below are
trustworthy.

Run `finrag eval` (or `python evals/run_evals.py`) to populate this table:

| tier | naive | graphrag | lightrag | Δ cost/query |
|---|---|---|---|---|
| local | — | — | — | — |
| multi_hop | — | — | — | — |
| global | — | — | — | — |

Cells are `mean correctness / mean completeness` (LLM-judge, 1-5 scale each). The full
report (`evals/results.md`) also has a cost/latency-per-mode table and a per-question
detail table with the judge's rationale for every cell.

## Observability

Every `finrag ask` (and every eval question × mode) opens a root `span("ask", ...)` in
`observability.py`, nests `classify`/`retrieve`/`generate` spans under it, and always writes
`runs/traces/{timestamp}_{trace_id}.jsonl` — the CLI's trailing `mode=... latency=...
cost=$...` line and `evals/results.md`'s cost/latency columns both come from that same
local trace, so nothing needs a network round trip to render.

Optionally, set three env vars and every span is *also* mirrored into
[Langfuse](https://cloud.langfuse.com) (free cloud tier, no card required):

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com   # default, only needed for self-hosted
```

With those set, `finrag ask "..."` shows up in the Langfuse UI as a trace named `ask`,
with `classify`/`retrieve`/`generate` as nested spans and each LLM call as its own
`generation` observation carrying the model name, input/output token counts, and cost —
computed from the same pricing table the local JSONL uses. Langfuse gives you the things a
local file can't: a searchable trace history across runs, cost/latency dashboards, and a UI
you can point a teammate at.

Leave the three env vars unset and nothing changes — the local JSONL trace is written
either way, `Langfuse(...)` is never constructed, and no network call is made. That's also
why the test suite needs no Langfuse account: `tests/test_observability.py` swaps in a
recording fake for the Langfuse client class to check the mirroring logic without ever
touching the real SDK's network path.

## Testing

```bash
pytest -q
```

The entire suite runs offline — no `ANTHROPIC_API_KEY`, no Docker, no network. LLM calls
are faked at the `llm.py` boundary (`FakeLLM`-style monkeypatches of `_get_client`), and
Neo4j is faked with an in-memory `FakeGraphStore` that implements the same `GraphStore`
protocol as the real `Neo4jGraphStore`. `tests/conftest.py` also redirects `data/` and
`runs/` to a per-test tmp path so nothing ever writes into the real project directories.

## What I'd build next

1. **Entity-description summarization on merge** — what LightRAG actually does when two
   chunks describe the same entity, instead of the concat-with-cap we do today.
2. **Incremental ingestion** — add a 7th company without rebuilding the graph, and
   contrast that with Microsoft GraphRAG needing a full community re-clustering.
3. **A FastAPI `POST /ask` endpoint** — the "user-facing application" checkbox.
4. **Hybrid mode** — lightrag's dual-level context with naive's top-k chunks appended, the
   LightRAG paper's "hybrid" retrieval level.
5. **Retrieval-level metrics** — chunk-recall against hand-labeled relevant chunks, to
   separate "retrieval failed" from "generation failed" when a question scores low.
