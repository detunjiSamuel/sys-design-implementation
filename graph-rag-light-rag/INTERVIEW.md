# Interview Playbook — "Tell me about a project you worked on"

How to present FinGraphRAG in an interview, plus prepared answers to the follow-ups you should
expect. Read this *after* building and running everything — several answers have blanks you must
fill with your real eval numbers, and every answer here only works if it's true in your hands.

**Ground rule: never say anything from this file you can't demo or defend.** If an interviewer
pushes one level deeper than a prepared answer, the prepared answer was worthless unless you
actually understand it. Use this file as a rehearsal script, not a cheat sheet.

---

## 1. The core answer (~90 seconds, spoken)

Structure: problem → decision → build → evidence → what you learned. Practice it out loud.

> "I built a question-answering system over SEC 10-K filings that compares three retrieval
> strategies side by side: standard vector RAG, GraphRAG, and LightRAG's dual-level retrieval.
>
> The motivating problem: vector RAG works fine when the answer sits in one chunk, but it breaks
> on questions like *'What risks do Apple and JPMorgan share?'* — no single chunk is similar to
> that question, because the answer is an aggregation across documents. So I built an ingestion
> pipeline that pulls 10-Ks from EDGAR, uses an LLM with structured outputs to extract entities
> and relationships into a Neo4j knowledge graph, and embeds both entities and relationship
> descriptions into a vector store. At query time, LightRAG-style retrieval splits the question
> into concrete entity keywords and thematic keywords — entities resolve to local graph
> neighborhoods via Cypher traversals, themes match against relationship descriptions — and the
> merged subgraph plus source chunks go to the model.
>
> The part I'm most proud of is the evaluation harness: 24 gold questions in three tiers — local,
> multi-hop, global — scored by an LLM judge for correctness and completeness, with latency and
> cost per query traced through Langfuse. The result: on local factoid questions all three
> strategies roughly tie, so naive RAG wins on cost — but on multi-hop and thematic questions,
> graph retrieval scored [YOUR NUMBERS] versus [YOUR NUMBERS] for naive. So my takeaway isn't
> 'graphs are better' — it's that I can now tell you *which* question types justify the extra
> indexing cost, with a table to back it up."

Why this shape works: it leads with a *failure mode* (shows judgment, not tutorial-following),
names concrete technologies without listing them, and ends on measurement — which is where most
candidate projects are weakest and where FDE interviews probe hardest.

**Fill in before your first interview:** run `finrag eval`, open `evals/results.md`, and replace
the bracketed placeholders with your actual per-tier means. If your numbers *don't* show the graph
winning on multi-hop, say that honestly and explain your diagnosis — a candidate who says "my
first eval run showed X, I traced it to Y" is more credible than one with suspiciously clean wins.

---

## 2. Follow-up questions and answers

### A. Why / mechanics

**"Why does naive RAG fail on multi-hop questions, mechanically?"**
Cosine similarity retrieves chunks that *look like the question*, not chunks that *compose into
the answer*. For "what risks do Apple and JPMorgan share?", the similarity mass lands on chunks
containing words like "risk" and one of the company names — you get Apple's risk chunks OR
JPMorgan's, ranked by surface similarity, and the top-k budget is rarely balanced across both.
The comparison itself — the "share" part — exists in no chunk, so no embedding can find it. The
graph fixes this by *pre-computing the connections at ingest time*: extraction already recorded
that both companies relate to "interest rate exposure", so retrieval is a lookup, not a hope.

**"What's actually different between GraphRAG and LightRAG?"**
Same core insight (extract a graph, retrieve structure), different indexing economics. Microsoft's
GraphRAG clusters the graph into communities and pre-writes LLM summaries of each — great for
global questions, but expensive to build and it must be re-clustered when documents change.
LightRAG skips community summaries entirely: the relationship *descriptions written at extraction
time* serve as the thematic index, queried through a second embedding space. That makes updates
incremental — extract the new document, merge nodes — and it's why my ingestion is idempotent
`MERGE`s rather than a batch rebuild. The trade: no pre-digested community summaries, so very
broad "summarize everything" questions lean harder on the generation step.

**"Explain dual-level retrieval like I'm not an ML person."**
The query gets split into two kinds of handles: *things* ("Apple", "TSMC") and *themes* ("supply
chain concentration"). Things are looked up in an index of entities and pull in their graph
neighborhoods — precise, local. Themes are looked up in an index of relationship descriptions —
fuzzy, global, because a theme like "regulatory exposure" appears in edges all over the graph.
Union the two and you get both the specific facts and the connective tissue.

### B. Architecture decisions

**"Walk me through your graph schema."**
Two node labels: `Entity` (name, type, description) and `Chunk` (the source text). Two edge
types: `RELATED` between entities — carrying a description, thematic keywords, and a 1–10
strength — and `MENTIONED_IN` from entity to chunk, which is the provenance link that lets every
answer cite its source text. Entity names are normalized and `MERGE`d, so "APPLE" extracted from
an NVIDIA filing and from Apple's own filing land on the same node — that's where cross-document
structure comes from.

**"Why are the embeddings in Chroma and not in Neo4j? Neo4j has vector indexes."**
Deliberate separation of concerns: Neo4j does what graphs are for (traversal), Chroma does what
vector stores are for (similarity), and the join key is trivial — Chroma doc IDs are entity names
and `SRC|DST` edge keys, so a vector hit converts to a graph lookup with no glue. Using Neo4j's
vector index would work, but it splits vector logic across two systems and adds index-config
surface for zero capability gain at this scale. If I were consolidating infra for a customer who
already runs Neo4j, I'd revisit — that's an ops decision, not a correctness one.

**"Why Neo4j at all? You could do this with networkx in memory."**
For this corpus size, honestly, you could — and my test suite effectively does (there's an
in-memory `FakeGraphStore` behind the same interface). I chose Neo4j because persistence and
Cypher were goals: the graph survives restarts, the browser makes the structure visually
inspectable — which was crucial for debugging extraction quality — and Cypher traversals are the
industry way to express "2-hop neighborhood ranked by edge weight". The interface means swapping
stores is a one-line change, which is also how the tests run without Docker.

**"Why LangGraph? Isn't that overkill for three steps?"**
Scoped deliberately: LangGraph runs *only* the query pipeline — classify → retrieve → generate —
where a state machine genuinely fits (conditional entry skips classification when the mode is
explicit; the routing is declared, not buried in if/else). I explicitly did *not* wrap ingestion
in it; ingestion is a plain script because a framework there would be resume-driven engineering.
Being able to say where a framework *isn't* worth it is the answer I'd want to hear.

**"Why one LLM provider? Why local embeddings?"**
One provider, one key, one failure domain — and `client.messages.parse()` with a Pydantic schema
gives validated structured output for extraction, which killed the whole JSON-repair class of
bugs. Embeddings are local (FastEmbed, ONNX, CPU) because the provider doesn't ship an embeddings
endpoint and adding a second paid API for it bought nothing — plus deterministic local embeddings
make the test suite hermetic.

### C. Evaluation (expect the deepest probing here)

**"How do you know the graph is actually better? Convince me."**
Three-tier question design, because "better" is question-dependent. Eight *local* questions
(answer in one chunk — my hypothesis: no graph advantage, and if the graph modes lose here that's
a red flag for added noise). Eight *multi-hop* (2–3 entities must be connected). Eight *global*
(themes across all six companies). Each has a gold answer I verified against the filings myself.
An LLM judge scores correctness and completeness 1–5 against the gold answer, and I track latency
and cost per query per mode. The claim I make is the per-tier delta, not a single blended number
— a blended number would let 8 easy questions hide the interesting result.

**"LLM-as-judge is unreliable. How do you defend it?"**
It has known failure modes and I designed around the ones I could: the judge sees the question,
the gold answer, and the candidate answer — *not* the retrieval context, so it can't be seduced
by impressive-looking context; scores are anchored to a written 1/3/5 rubric, not vibes; and the
gold answers are human-verified. What I'd add with more time: spot-check a sample by hand against
judge scores, swap answer ordering to detect position bias, and a second judge model for
agreement. The honest summary: LLM-judge is fine for *comparing systems on the same questions* —
relative deltas — and weak for absolute quality claims. I only use it for the former.

**"Your resume says X% improvement. Where does that number come from?"**
Be ready to point at `evals/results.md` and compute the number live: it's the multi-hop/global
tier delta between lightrag and naive mean correctness. If you haven't run the eval, do not cite
a number — an FDE interviewer will ask to see the table, and "let me show you" is a winning
moment while "it's approximate" is a losing one.

### D. Observability & operations

**"Walk me through a trace."**
Every query opens a root span; retrieval and generation are child spans; each LLM call is
recorded as a generation with model and token counts, and cost is computed from a pricing table.
Two backends off the same instrumentation: Langfuse when keys are configured — hosted UI, trace
history, per-generation cost — and a local JSONL file always, which is what the eval harness
reads synchronously. So for "why did that query cost 4 cents and take 9 seconds", I open the
Langfuse trace and read the tree: usually one embedding call, one keyword-extraction call
(lightrag only), a Cypher round-trip, and one big generation call that dominates both time and
cost. (Then actually do this in the demo — see `demo.md`.)

**"Where does the money go, per query and per corpus?"**
Ingestion is the big one: one extraction call per chunk, a few hundred chunks per corpus — it's
the only step that costs real dollars, which is why it's checkpointed to disk and resumable
(never re-pay for chunk 1–399 because 400 crashed). Per query: naive pays for one generation
call; lightrag adds one small keyword-extraction call — a few percent extra — and buys the
multi-hop accuracy. To cut extraction cost 5×, the model is a config knob: point extraction at a
small model, re-run the eval, and *measure* the quality delta instead of guessing. That
cost-quality knob plus the eval harness to price it is exactly the conversation an FDE has with
a customer.

**"How does this run in CI with no API key and no database?"**
The LLM and the graph store are each behind a thin module boundary — `llm.py` is the only file
that imports the SDK, and `GraphStore` is a Protocol with a real Neo4j implementation and an
in-memory fake. Tests monkeypatch the LLM at that boundary and use the fake store, so the full
suite (67 tests) runs offline in seconds. That was a constraint from day one, not a retrofit.

### E. Hard-mode questions (weaknesses — own them)

**"Two entities with the same name that are different things. What happens?"**
They incorrectly merge — entity resolution is the known weak point of name-keyed graphs. My
mitigations are honest but partial: type-qualified canonical names from a controlled entity-type
vocabulary, and descriptions that concatenate on merge so a human (or judge) can spot a chimera
node. Real fixes I'd do next: embedding-similarity check before merging (block the merge if the
two descriptions are dissimilar), or entity linking against an external ID system like SEC CIK
numbers — which this corpus conveniently has.

**"What happens at 10,000 documents?"**
Three things break in order. (1) Extraction cost — linear in chunks; answer is a cheaper
extraction model and batch processing. (2) Neighborhood explosion — 2-hop around a hub node like
"APPLE" returns half the graph; I already cap by edge strength, but at scale you need degree-aware
traversal or community detection — which is exactly the point where Microsoft GraphRAG's
community summaries start earning their cost, and I can say precisely where that line is.
(3) Entity resolution noise compounds — see previous answer. What *doesn't* break: the query path
stays fast because retrieval is index lookups plus a bounded traversal, not a corpus scan.

**"Is this production-grade?"**
Frame it as: production-*shaped*, honestly scoped. It has the things production systems need that
tutorials skip — idempotent resumable ingestion, tracing with cost attribution, hermetic tests,
config-not-code for every knob, graceful per-chunk failure handling. What it doesn't have, and
I know it: authn/multi-tenancy, retry budgets and rate-limit handling beyond SDK defaults, a
serving layer (CLI only), and eval regression gates in CI. If asked to productionize, that list
is my roadmap — starting with a FastAPI layer and CI eval gates.

**"What was the hardest bug / what surprised you?"**
Have two real stories. Suggested candidates from this build (verify against your own experience —
tell YOUR version): (1) Real-world data mess: EDGAR filings are inconsistent — sections missing
or renamed per company — so the ingester logs-and-continues instead of failing, and that decision
(skip vs abort) is visible in traces. (2) Subtle store-parity bug: the in-memory fake store
honored `hops=0` exactly while the Neo4j implementation floored it at 1, so the same retriever
behaved slightly differently in tests vs live — caught it during live verification, documented
the divergence. The lesson: a fake that drifts from the real implementation is worse than no
fake, so parity needs its own tests. (3) Chroma metadata only accepts scalars — keyword lists had
to be flattened to comma-joined strings; small, but typical of integration reality.

**"What would you do differently if you started over?"**
Pick 2–3 and mean them: write the eval questions *first* (they define done — I wrote them last
and it showed me gaps in what I'd extracted); LLM-summarize entity descriptions on merge instead
of concat-with-cap (what LightRAG actually does; my version degrades on high-degree entities);
retrieval-level metrics (chunk recall) separate from answer quality, so "retrieval failed" vs
"generation failed" is diagnosable from the eval table instead of by reading transcripts.

### F. Behavioral hooks this project supports

- **"Tell me about a time you made a trade-off"** → community summaries vs relationship-index
  (build cost vs global-question quality); concat-vs-summarize on merge; judge-only evals vs
  human labeling. Use the decision table in PLAN.md — every row is a rehearsed trade-off story.
- **"Tell me about debugging something hard"** → the store-parity story above, plus how tracing
  (span attrs recording dropped chunks, keywords, seed entities) made retrieval debuggable.
- **"How do you decide what NOT to build?"** → no framework on ingestion, no Neo4j vector index,
  no async, hand-written gold answers instead of synthetic ones. Simplicity as a feature.
- **"How would you explain this to a non-technical customer?"** → the dual-level explanation in
  section A, plus the results table: "for these question types, the cheap thing is fine; for
  these, the graph pays for itself."

---

## 3. Prep checklist before the interview

- [ ] Run the full pipeline end to end yourself, including `finrag eval`; fill in the bracketed
      numbers in section 1 from `evals/results.md`.
- [ ] Verify every gold answer in `evals/questions.yaml` against the actual filings (they ship
      as drafts — this is also how you learn the corpus well enough to survive follow-ups).
- [ ] Rehearse the 90-second answer out loud until it's 90 seconds.
- [ ] Rehearse the live demo (`demo.md`): naive failure → Neo4j browser → lightrag success →
      Langfuse trace → results table. Ten minutes, practiced twice.
- [ ] Replace the "hardest bug" stories with what *actually* bit you during your build.
- [ ] Re-read PLAN.md section 3 (decision log) and section 7 (question bank) the night before.
