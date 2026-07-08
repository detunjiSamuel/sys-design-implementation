# FinGraphRAG — Knowledge Graph RAG over SEC 10-K Filings

**An implementation guide for building (and being able to defend) a comparative RAG system: Naive RAG vs GraphRAG vs LightRAG.**

This document is written for you, the builder. Every design choice has a "why" attached, because the interview
question is never "did you build it" — it's "why did you build it *that way*, and what would you change".

---

## 1. What we're building and why

**One sentence:** a Python system that ingests SEC 10-K annual reports, builds a knowledge graph from them
using LLM-driven entity extraction, and answers questions through three interchangeable retrieval strategies —
naive vector RAG, GraphRAG, and LightRAG-style dual-level retrieval — with an evaluation harness that measures
which strategy wins on which class of question.

**Why this project covers the FDE job requirements:**

| FDE requirement | Where it shows up here |
|---|---|
| Building, testing, deploying software in a real-world environment | Real messy data (EDGAR HTML), Docker-run database, CLI tooling, offline test suite |
| Working across the stack: databases, APIs, data pipelines, model integration | Neo4j (graph DB) + Chroma (vector DB), Anthropic API, EDGAR ingestion pipeline, LangGraph orchestration |
| LLM workflows, data pipelines, evals | LLM extraction pipeline, dual-level retrieval, LLM-as-judge eval harness, cost/latency tracing |

**The comparison angle is the whole point.** Anyone can follow a LightRAG tutorial. What makes this defensible
is being able to say: "on local factoid questions all three tie, so naive RAG wins on cost; on multi-hop and
thematic questions, graph retrieval wins by X points, and here is the eval table that proves it." That is
exactly how a Forward Deployed Engineer talks to a customer: recommend the *simplest* thing that meets the
requirement, with evidence.

---

## 2. The 60-second conceptual primer

**Naive RAG:** chunk documents → embed chunks → at query time, embed the question and fetch the top-k most
cosine-similar chunks → stuff them into the prompt. Fails when the answer is *spread across* documents
("Which risks do Apple and JPMorgan share?") because no single chunk is similar to the question.

**GraphRAG (Microsoft-style, simplified):** at ingest time, an LLM extracts entities and relationships from
every chunk, forming a knowledge graph. At query time, link the question to seed entities, expand the
neighborhood in the graph (k-hop traversal), and hand the model the connected entities, relationships, and
their source chunks. The graph *pre-computes the connections* that naive RAG hopes to find by luck.

**LightRAG (the methodology we implement):** GraphRAG's insight, made cheap. Two ideas:
1. **Dual-level retrieval.** An LLM splits the query into *low-level keywords* (concrete entities: "Apple",
   "TSMC") and *high-level keywords* (themes: "supply chain concentration", "regulatory risk"). Low-level
   keywords match against **entity** embeddings → local graph neighborhoods. High-level keywords match against
   **relationship-description** embeddings → global thematic edges. The union becomes the context.
2. **No expensive community-summarization step.** Microsoft's GraphRAG clusters the graph and pre-summarizes
   communities (costly to build and rebuild). LightRAG skips that: relationship descriptions written at
   extraction time *are* the thematic index. Incremental updates are just "extract the new doc, merge nodes".

Say this in an interview: *"GraphRAG answers 'global' questions by pre-computing structure; LightRAG keeps
that ability but makes indexing incremental and an order of magnitude cheaper by indexing relationships
directly instead of building community summaries."*

---

## 3. Design decisions (the architect's log)

Every one of these is a question you should be able to answer under interrogation.

| Decision | Choice | Why (and what was rejected) |
|---|---|---|
| Financial niche | SEC 10-K annual reports, sections 1 (Business), 1A (Risk Factors), 7 (MD&A), ~6 companies across sectors (AAPL, MSFT, NVDA, JPM, XOM, PFE) | Free, no auth (EDGAR), genuinely unstructured, and entity-rich. Cross-sector on purpose: shared themes (rates, supply chain, regulation) create real multi-hop questions. Rejected: earnings-call transcripts (paywalled), news (no stable corpus). |
| LLM | Anthropic Claude via the official `anthropic` SDK; model configurable, default `claude-opus-4-8` | One provider, one key. `client.messages.parse()` gives Pydantic-validated structured output for extraction — no JSON-repair hacks. Model is a config knob so extraction can be pointed at a cheaper model if cost matters. |
| Embeddings | FastEmbed (`BAAI/bge-small-en-v1.5`), local, CPU | Anthropic has no embeddings endpoint. FastEmbed is ONNX-based (no torch install), free, deterministic, and runs offline — which also makes tests hermetic. Rejected: OpenAI embeddings (second API key for no pedagogical gain). |
| Vector store | Chroma (embedded, persistent) | Zero-ops: it's a library, not a server. We pass our own embeddings explicitly so nothing is magic. Three collections: `chunks`, `entities`, `relations`. Rejected: pgvector/Qdrant (server to run, no clarity gain at this scale). |
| Graph store | Neo4j Community via docker-compose | The resume bullet says Cypher, and Cypher reads like pseudocode — perfect for explaining traversals. A `FakeGraphStore` (in-memory dict of nodes/edges) implements the same interface for tests. |
| Orchestration | LangGraph `StateGraph` for the query pipeline only | Real value: the query flow is a small state machine (classify → retrieve → generate) and LangGraph makes the routing explicit and inspectable. Deliberately NOT used for ingestion — ingestion is a plain script; wrapping it in a framework would be resume-driven engineering. Chunking uses `langchain-text-splitters` (small, genuinely useful). |
| Observability | Hand-rolled: a `trace` module writing JSONL spans (stage, latency, tokens, cost) + a console summary | An FDE must answer "why is this query slow/expensive" on a customer call. Building the tracing yourself means you understand what a span *is*. LangSmith/Langfuse are one env var away later; starting with them hides the mechanics. |
| Evals | ~24 gold questions in 3 tiers (local / multi-hop / global), LLM-as-judge scoring correctness & completeness, plus latency and cost per query per mode | The eval harness is the deliverable that powers the comparison claim. Tiered questions are the experiment design: each tier is a hypothesis about where graphs help. |
| Testing | pytest, `FakeLLM` + `FakeGraphStore`, no network/docker needed | FDE reality: CI can't have your API key or a database. Faking at the boundary (our own thin wrappers) keeps tests fast and free. |
| Code style | Plain functions and small classes, type hints, no inheritance trees, no async | A new grad should be able to hold every module in their head. Cleverness is a cost. |

---

## 4. Architecture

### 4.1 Repository layout

```
graph-rag-light-rag/
├── PLAN.md                     # this document
├── README.md                   # quickstart + results table
├── pyproject.toml              # deps + `finrag` console script (src layout)
├── docker-compose.yml          # neo4j:5-community
├── .env.example                # ANTHROPIC_API_KEY, NEO4J_*, model names
├── src/finrag/
│   ├── config.py               # pydantic-settings; every knob lives here
│   ├── models.py               # Pydantic data shapes shared by all modules
│   ├── llm.py                  # THE ONLY file that talks to the Anthropic API
│   ├── embeddings.py           # THE ONLY file that computes embeddings
│   ├── observability.py        # span() context manager, JSONL traces, cost math
│   ├── ingest/
│   │   ├── download.py         # EDGAR → data/raw/{ticker}_{section}.txt
│   │   └── chunk.py            # raw text → data/chunks.jsonl
│   ├── extract.py              # chunks → entities/relations (LLM, structured output)
│   ├── stores/
│   │   ├── vector_store.py     # Chroma wrapper: 3 collections
│   │   └── graph_store.py      # Neo4jGraphStore + FakeGraphStore (same interface)
│   ├── retrievers/
│   │   ├── base.py             # the shared 5-line interface
│   │   ├── naive.py            # vector top-k
│   │   ├── graph_rag.py        # entity linking + k-hop expansion
│   │   └── light_rag.py        # dual-level keyword retrieval
│   ├── pipeline.py             # LangGraph: classify → retrieve → generate
│   ├── answer.py               # prompt assembly + citation-grounded generation
│   └── cli.py                  # typer: download, chunk, build-graph, index, ask, eval
├── evals/
│   ├── questions.yaml          # gold set, tiered
│   └── run_evals.py            # runs 3 modes × N questions, judges, writes report
├── data/                       # gitignored artifacts (raw/, chunks.jsonl, chroma/)
└── tests/                      # offline unit tests with fakes
```

### 4.2 Data flow

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

### 4.3 Graph schema (Neo4j)

```cypher
(:Entity  {name, type, description})           // type ∈ COMPANY, PERSON, PRODUCT, RISK, REGULATION, METRIC, ...
(:Chunk   {id, company, section, text})
(:Entity)-[:RELATED {description, keywords, strength}]->(:Entity)
(:Entity)-[:MENTIONED_IN]->(:Chunk)
```

Notes:
- Entity names are normalized (upper-cased, stripped) and **merged** on re-extraction — `MERGE` in Cypher.
  When two chunks describe the same entity, descriptions are concatenated (LightRAG does an LLM-summarize
  step here; we keep concat-with-cap for simplicity and note it as a stretch goal).
- Embeddings live in Chroma, not Neo4j. Chroma doc IDs = entity name / relation "src|dst" key, so a vector
  hit converts to a graph lookup with no joins. (Rejected: Neo4j vector indexes — more config, splits the
  vector logic across two systems.)
- `strength` is a 1–10 LLM-assigned weight, used to rank edges when the neighborhood is too big.

### 4.4 Module contracts (what each file exposes)

Keep these signatures — they are what makes the three retrievers swappable and the system testable.

```python
# models.py
class Chunk(BaseModel):        id: str; company: str; section: str; text: str
class Entity(BaseModel):       name: str; type: str; description: str
class Relation(BaseModel):     source: str; target: str; description: str; keywords: list[str]; strength: int
class Extraction(BaseModel):   entities: list[Entity]; relations: list[Relation]   # LLM output schema
class QueryKeywords(BaseModel): low_level: list[str]; high_level: list[str]        # LLM output schema
class RetrievalResult(BaseModel): chunks: list[Chunk]; entities: list[Entity]; relations: list[Relation]
class Answer(BaseModel):       text: str; citations: list[str]; mode: str

# llm.py  — wraps anthropic.Anthropic(); records usage into the active trace span
def complete(system: str, user: str, model: str | None = None) -> str
def extract(system: str, user: str, schema: type[T], model: str | None = None) -> T   # messages.parse

# embeddings.py
def embed(texts: list[str]) -> list[list[float]]      # fastembed, cached singleton model

# stores/vector_store.py
class VectorStore:                                     # one Chroma PersistentClient
    def add(self, collection: str, ids: list[str], texts: list[str], metadatas: list[dict]) -> None
    def query(self, collection: str, text: str, k: int) -> list[tuple[str, str, dict, float]]  # (id, text, meta, score)

# stores/graph_store.py — Neo4jGraphStore and FakeGraphStore both implement:
class GraphStore(Protocol):
    def upsert_entity(self, e: Entity) -> None
    def upsert_relation(self, r: Relation) -> None
    def link_mention(self, entity_name: str, chunk: Chunk) -> None
    def neighborhood(self, names: list[str], hops: int = 1) -> tuple[list[Entity], list[Relation]]
    def chunks_for_entities(self, names: list[str], limit: int) -> list[Chunk]

# retrievers/base.py — the whole interface
class Retriever(Protocol):
    name: str
    def retrieve(self, question: str) -> RetrievalResult

# pipeline.py — LangGraph
def build_pipeline() -> CompiledStateGraph   # State: {question, mode, result, answer}
def ask(question: str, mode: str = "auto") -> Answer
```

---

## 5. Implementation phases

Each phase has a **goal**, **steps**, and a **definition of done** you can demo. Do them in order; each
phase produces something runnable.

### Phase 0 — Scaffold and plumbing
**Goal:** empty-but-runnable project: config, CLI skeleton, docker, tests pass.
- `pyproject.toml` (src layout, console script `finrag`), `.env.example`, `docker-compose.yml` for Neo4j
  (with a named volume; expose 7474/7687; `NEO4J_AUTH=neo4j/password` from env).
- `config.py` with pydantic-settings: API key, model names (`answer_model`, `extract_model`, `judge_model`
  — all default `claude-opus-4-8`), Neo4j URI/auth, chunk size/overlap, top-k values, data paths, pricing
  table for cost math.
- `llm.py`, `embeddings.py`, `models.py`, `observability.py` with tests using a `FakeLLM`.
- **Done when:** `pip install -e .` works, `finrag --help` lists commands, `pytest` is green with no
  network, `docker compose up -d` gives a browsable Neo4j at localhost:7474.

### Phase 1 — Ingestion pipeline
**Goal:** real 10-K text on disk, chunked and reproducible.
- `download.py` using `edgartools`: for each ticker, fetch the latest 10-K, extract Items 1, 1A, 7, write
  plain text to `data/raw/`. Idempotent (skip if file exists). EDGAR requires a User-Agent identity string —
  read it from config. Handle a missing section gracefully (log and continue — real filings are inconsistent;
  this is FDE life).
- `chunk.py`: RecursiveCharacterTextSplitter, ~4000 chars with 400 overlap, stable chunk IDs
  (`{ticker}_{section}_{n}`), write `data/chunks.jsonl`.
- **Done when:** `finrag download && finrag chunk` produces ~300–600 chunks; rerunning changes nothing.

### Phase 2 — Naive RAG baseline
**Goal:** end-to-end Q&A the "normal" way. This is the baseline everything is measured against.
- `vector_store.py`; `finrag index` embeds all chunks into Chroma.
- `retrievers/naive.py`: embed question, top-k chunks, done.
- `answer.py`: prompt that (a) forbids answering outside the provided context, (b) requires `[chunk_id]`
  citations. One function: `generate(question, result: RetrievalResult, mode) -> Answer`.
- **Done when:** `finrag ask "What does Apple say about supply chain risk?" --mode naive` gives a cited
  answer. Then ask *"What risks do Apple and JPMorgan share?"* and **save the (bad) output** — that failure
  is your demo motivation for the graph.

### Phase 3 — Graph construction (the LightRAG ingest side)
**Goal:** a knowledge graph in Neo4j built by LLM extraction.
- `extract.py`: per chunk, call `llm.extract(..., schema=Extraction)` with a prompt that defines entity
  types, asks for relationship descriptions + keywords + strength 1–10. Batch with progress bar, checkpoint
  to `data/extractions.jsonl` so a crash doesn't re-pay for finished chunks (idempotent resume).
- `graph_store.py`: `MERGE`-based upserts; description concat-with-cap on entity collisions.
- `finrag build-graph`: read extractions → upsert into Neo4j → embed entity descriptions into Chroma
  `entities` and relation descriptions into Chroma `relations`.
- **Done when:** Neo4j browser shows the graph; you can run
  `MATCH (e:Entity {name:"TSMC"})-[r:RELATED]-(x) RETURN e,r,x` and see cross-company structure;
  extraction of ~400 chunks completes with cost printed at the end.

### Phase 4 — Graph retrievers
**Goal:** the two graph-based strategies, behind the same interface as naive.
- `graph_rag.py`: vector-match the question against `entities` (top ~5 seeds) → `neighborhood(seeds, hops=2)`
  → `chunks_for_entities` → RetrievalResult with entities + relations + chunks. Rank edges by `strength`,
  cap context size.
- `light_rag.py`: `llm.extract(question, schema=QueryKeywords)` → low-level keywords query `entities`
  collection (local view), high-level keywords query `relations` collection (global view) → union the
  neighborhoods, dedupe, cap. The context string the generator sees has three labeled sections:
  entities table, relations table, source chunks (this mirrors the LightRAG paper's context format).
- **Done when:** the shared-risk question that failed in Phase 2 now gets a correct, multi-company answer
  under `--mode lightrag`, and `--mode graphrag` also improves over naive.

### Phase 5 — Pipeline + DX
**Goal:** one entry point, explicit flow, good ergonomics.
- `pipeline.py`: LangGraph StateGraph — `classify` node (LLM labels the question local/multi-hop/global;
  auto-picks a retriever, or is bypassed when `--mode` is explicit) → `retrieve` → `generate`.
- `finrag ask` uses the pipeline; `--mode auto|naive|graphrag|lightrag`; `--show-context` flag prints what
  the model saw (indispensable for debugging retrieval); every query prints a one-line trace summary:
  `mode=lightrag latency=3.2s tokens=8.1k cost=$0.041 trace=runs/traces/...jsonl`.
- **Done when:** `finrag ask "..."` works end to end with tracing, and `--mode auto` routes sensibly.

### Phase 6 — Evaluation harness (the payoff)
**Goal:** the table that justifies the whole project.
- `evals/questions.yaml`: ~24 questions — 8 **local** (answer in one chunk: "What was NVIDIA's data center
  revenue driver?"), 8 **multi-hop** (2–3 entities: "How does TSMC dependence connect Apple and NVIDIA's
  risk factors?"), 8 **global** ("What common macroeconomic risks appear across all six companies?").
  Each has a `gold` reference answer written by *you, after reading the filings* (that act teaches you the
  corpus — do not delegate it to an LLM without review).
- `run_evals.py`: for each question × each mode → answer → LLM judge scores correctness (1–5) and
  completeness (1–5) against the gold answer (judge sees gold + answer, not the retrieval) → collect
  latency + token cost from traces → write `evals/results.md` with a per-tier table and per-question detail.
- **Done when:** you have a results table like — and can explain every cell of it:

  | tier | naive | graphrag | lightrag | Δ cost/query |
  |---|---|---|---|---|
  | local | ~tie | ~tie | ~tie | naive cheapest |
  | multi-hop | low | high | high | graph pays off |
  | global | low | high | high | graph pays off |

### Phase 7 — README + demo script
**Goal:** a stranger (or interviewer) can run and understand it in 10 minutes.
- README: what/why, architecture diagram, quickstart (5 commands), the results table, "what I'd do next".
- A `demo.md` walkthrough: the naive failure → the graph in the Neo4j browser → the lightrag success →
  the eval table. That is your interview story arc.

### Stretch goals (do after everything works; each is a good conversation piece)
1. **Entity-description summarization** on merge (what LightRAG actually does) instead of concat.
2. **Incremental ingestion**: add a 7th company without rebuilding — show the graph merge; contrast with
   Microsoft GraphRAG needing community re-clustering.
3. **FastAPI endpoint** (`POST /ask`) — the "user-facing application" checkbox.
4. **Hybrid mode**: lightrag context + naive chunks appended (LightRAG paper's "hybrid" level).
5. **Retrieval-level metrics**: chunk-recall against hand-labeled relevant chunks, so you can separate
   "retrieval failed" from "generation failed" — the first question a real debugging session asks.

---

## 6. Observability & cost accounting (FDE material, not an afterthought)

- `observability.py` exposes `span(name, **attrs)` — a context manager. Nested spans share a trace ID.
  Each span records: name, wall-clock ms, and (for LLM spans) model, input/output tokens, computed cost
  from the pricing table in config.
- Every `finrag ask` writes `runs/traces/{timestamp}_{trace_id}.jsonl` — one line per span — and prints a
  summary line. The eval harness aggregates these files; nothing is measured twice.
- Failure handling policy (keep it boring): LLM calls get the SDK's built-in retries; extraction failures
  for a single chunk are logged and skipped (never abort a 400-chunk run at chunk 399); every skip is
  visible in the trace.

**Why hand-rolled:** when a customer asks "why did that query cost 4 cents and take 9 seconds", you open one
JSONL file and read the spans. When you later adopt Langfuse/LangSmith at a real job, you'll know exactly
what those products are doing for you.

---

## 7. Questions you should be able to answer when this is done

Architecture: Why three collections in Chroma? Why are embeddings not in Neo4j? Why is `llm.py` the only
file that imports `anthropic`? What breaks if two entities with the same name are actually different things
(entity resolution — what's your mitigation)?

Methodology: What exactly is "dual-level" in LightRAG? What does Microsoft GraphRAG's community
summarization buy that we skipped, and when would you need it? Why does naive RAG fail multi-hop questions
*mechanically* (talk about where the similarity mass lands)?

Evals: Why tiered questions? Why does the judge see the gold answer but not the retrieved context? What are
the failure modes of LLM-as-judge and how would you sanity-check it (spot-check, swap positions, second
judge model)?

Ops: What does a trace span contain? Where does the money go per query in each mode (lightrag pays for one
extra small LLM call at query time — is it worth it)? How would you cut extraction cost 5× (cheaper model
for extraction — it's a config knob; measure quality delta with the eval harness)?

---

## 8. Runbook (once everything is built)

```bash
cp .env.example .env            # add ANTHROPIC_API_KEY
docker compose up -d            # Neo4j
pip install -e ".[dev]"
finrag download && finrag chunk # Phase 1: ~5 min, no LLM cost
finrag index                    # Phase 2: local embeddings, free
finrag extract                  # Phase 3: the LLM-cost step (~$2–10 depending on model)
finrag build-graph
finrag ask "What risks do Apple and JPMorgan share?" --mode naive     # watch it fail
finrag ask "What risks do Apple and JPMorgan share?" --mode lightrag  # watch it work
python evals/run_evals.py       # the table
pytest                          # offline, always green
```
