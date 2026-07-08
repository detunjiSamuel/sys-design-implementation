# Demo script

Presenter notes for a ~10-minute interview walkthrough of FinGraphRAG. The story arc: show
naive RAG fail mechanically → show the graph that fixes it → show lightrag succeed → show
the eval table that proves it's not a cherry-picked example → talk cost tradeoffs. Rehearse
this end to end once against a live environment before presenting it live; the exact
numbers you get will differ from any numbers written here as placeholders.

Assumes the runbook in `README.md` has already been run once: `finrag download && finrag
chunk && finrag index && finrag extract && finrag build-graph`, and Neo4j is up
(`docker compose up -d`).

---

## 1. Naive RAG fails on a cross-company question

Run:

```bash
finrag ask "What risks do Apple and JPMorgan share?" --mode naive --show-context
```

**Say while it runs:** "Naive RAG embeds the question, pulls the top-k most
cosine-similar chunks, and stuffs them into the prompt. That works when one chunk *is*
the answer. This question asks about two companies at once, and no single chunk in either
filing talks about both — so watch what happens."

**What to point at in the output:**
- `--show-context` prints the exact chunks the model saw. Walk through them: they'll be
  mostly Apple chunks *or* mostly JPMorgan chunks (whichever ticker's language happens to
  be closer in embedding space to the question), not a balanced mix of both.
- The answer itself: either it answers about one company and ignores the other, hedges
  ("I don't have enough context to compare both companies"), or invents a shared risk that
  isn't actually grounded in both filings' text.
- The trace summary line at the bottom (`mode=naive latency=... cost=...`) — note the cost;
  you'll come back to this number in step 5.

**Say:** "This isn't a prompting problem, it's a retrieval problem — the similarity mass
never lands on chunks that connect the two companies, because at ingest time we never
computed that connection. That's the motivation for the graph."

## 2. Open the Neo4j browser and show the graph

Open `http://localhost:7474` (default auth `neo4j` / `password`, or whatever
`NEO4J_PASSWORD` is set to). Run these Cypher queries live, one at a time:

**Query 1 — the graph exists and is cross-company:**
```cypher
MATCH (e:Entity {name: "TSMC"})-[r:RELATED]-(x:Entity)
RETURN e, r, x
```
**Say:** "TSMC is one node. Everything connected to it — Apple, NVIDIA, other suppliers —
was extracted independently from each company's own filing, but they merge onto the same
node because entity names are normalized and `MERGE`d in Cypher. This is the structure
naive RAG has no equivalent of."

**Query 2 — the shared-risk question, answered structurally:**
```cypher
MATCH (a:Entity {name: "APPLE INC"})-[:RELATED]-(shared:Entity)-[:RELATED]-(j:Entity {name: "JPMORGAN CHASE"})
RETURN a, shared, j
```
(Adjust entity names to whatever the actual extraction normalized them to — check with
`MATCH (e:Entity) WHERE e.name CONTAINS "APPLE" RETURN e.name` first if unsure.)

**Say:** "This is a 2-hop traversal: entities connected to both Apple and JPMorgan. That's
literally the question we asked in step 1, expressed as a graph query instead of a vector
search — and it's exactly what `graphrag`'s retriever does under the hood before handing
the results to the LLM to write up in prose."

**Query 3 — where the source text lives:**
```cypher
MATCH (e:Entity {name: "TSMC"})-[:MENTIONED_IN]->(c:Chunk)
RETURN c.id, c.company, left(c.text, 200)
```
**Say:** "Every entity keeps a pointer back to the chunk(s) it came from, so answers stay
citable — the graph isn't a black box summarizing away the source text, it's an index into
it."

## 3. LightRAG succeeds on the same question

Run:

```bash
finrag ask "What risks do Apple and JPMorgan share?" --mode lightrag --show-context
```

**Say while it runs:** "LightRAG splits the question into low-level keywords — concrete
entities like 'Apple', 'JPMorgan' — and high-level keywords — themes like 'macroeconomic
risk', 'regulatory exposure'. Low-level keywords search the entities index and expand one
hop in the graph; high-level keywords search relationship *descriptions* directly. Union
the two, and that's the context."

**What to point at:**
- `--show-context`: the ENTITIES and RELATIONSHIPS sections are now populated (naive's
  context was chunks only) — point out a relationship description that explicitly
  mentions both companies or a shared theme.
- The answer: it should name a specific shared risk (e.g. macro/rate sensitivity,
  regulatory scrutiny, or a shared counterparty/supplier if one exists in the corpus) with
  citations back to chunks from *both* filings.
- The trace line's cost vs. naive's from step 1 — call out the delta, then bridge to step 5.

## 4. The eval table

Run (or have already run and just show the file):

```bash
python evals/run_evals.py
cat evals/results.md
```

**Say:** "The demo question is one example — the eval table is 24 questions in three
tiers, so the claim isn't 'graphs are better,' it's 'graphs are better *on this class* of
question, tied on that class, and here's the LLM-judge score and the cost delta that prove
it, not just this one cherry-picked example.'"

Walk the headline table tier by tier:
- **local** — expect naive ≈ graphrag ≈ lightrag. "No multi-hop structure to exploit, so
  the extra complexity buys nothing — naive should win on cost here."
- **multi_hop** — expect graphrag and lightrag ahead of naive. "This is exactly the TSMC/
  Apple/NVIDIA and rates/JPMorgan/ExxonMobil kind of question — pre-computed structure
  should show up as a real score gap."
- **global** — expect lightrag ahead, possibly ahead of graphrag too. "This is the tier
  LightRAG's high-level index was built for — thematic questions spanning most of the
  corpus, where even a 2-hop graph walk from a handful of seed entities may not reach far
  enough, but the relationship-description index was built to be searched thematically."

Then the cost/latency table: "Naive is cheapest per query everywhere — one embedding call,
no LLM. Graphrag adds an entity-linking vector search plus the graph traversal. Lightrag
adds one extra small LLM call per query for keyword extraction. That's the one line item
worth defending: is one extra LLM call at query time worth the completeness/correctness
gain on multi-hop and global questions? The eval table is what answers that, not intuition."

## 5. Cost/latency tradeoff talking points

Have these ready as follow-up answers, not necessarily as scripted lines:

- **"Where does the money go per query in each mode?"** Naive: one embedding (free, local
  FastEmbed) + one generation call. Graphrag: one embedding for entity linking + Cypher
  traversal (free) + one generation call. Lightrag: one small LLM call to extract
  low/high-level keywords + embeddings for each keyword (free) + one generation call — the
  keyword-extraction call is the only added LLM cost lightrag pays over graphrag.
- **"Is that extra call worth it?"** Point at the eval table's multi-hop/global rows vs.
  the cost table — if the completeness/correctness delta is large and the added cost is a
  fraction of a cent, yes; if a tier shows no lift, that tier should route to naive
  (`pipeline.py`'s `--mode auto` classify step already does this routing automatically).
- **"How would you cut extraction cost 5x?"** `extract_model` in `config.py` is a config
  knob — point it at a cheaper model, re-run `finrag extract`, re-run `finrag eval`, and
  compare the eval table before/after. Cost is measured, not assumed.
- **"What's the failure mode of LLM-as-judge, and how do you sanity-check it?"** Spot-check
  a sample of judged answers by hand, consider running the judge twice with gold/candidate
  positions swapped to check for a position bias, and consider a second judge model to
  check for a same-model bias (the judge and the answer generator are the same model
  family here, which is worth disclosing, not hiding).
