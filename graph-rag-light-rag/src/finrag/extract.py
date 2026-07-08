"""chunks -> entities/relations, via LLM structured output. The LightRAG "ingest side".

`extract_chunk` calls the LLM once per chunk with `schema=Extraction` (see llm.py's
`extract()` -- `client.messages.parse()` under the hood, so the output is already a
validated `Extraction`, no JSON-repair needed). `extract_all` is the checkpointed batch
runner: it can be killed and re-run without re-paying for chunks already done.

`build_graph` then loads everything back off disk and upserts it into a `GraphStore`.
Embedding entity/relation descriptions into Chroma is a separate, later step -- see the
docstring on `build_graph` below for why it doesn't happen here.
"""

import json

from rich.console import Console
from rich.progress import Progress

from finrag.config import settings
from finrag.ingest.chunk import load_chunks
from finrag.llm import extract as llm_extract
from finrag.models import Chunk, Entity, Extraction, Relation
from finrag.observability import span
from finrag.stores.graph_store import GraphStore

EXTRACTION_SYSTEM_PROMPT = """\
You are building a knowledge graph from excerpts of SEC 10-K annual reports (Items 1 \
Business, 1A Risk Factors, and 7 MD&A). Read the excerpt and extract every entity and \
relationship that is explicitly stated or clearly implied in the text.

Entity types (use exactly one of these for each entity):
COMPANY, PERSON, PRODUCT, TECHNOLOGY, RISK, REGULATION, METRIC, EVENT, LOCATION, SECTOR.

For each entity, give:
- name: a short, canonical name (e.g. "Apple Inc.", not "the Company"; "TSMC", not \
"Taiwan Semiconductor Manufacturing Company, its primary chip supplier").
- type: one of the types above.
- description: one to two sentences, grounded in the text -- do not invent facts that \
aren't in the excerpt.

For each relationship between two extracted entities, give:
- source, target: must exactly match entity names you extracted above.
- description: one self-contained sentence explaining HOW the two entities relate. It \
should make sense on its own, without the surrounding text (a reader will see only this \
sentence, not the original excerpt).
- keywords: 3-6 short thematic phrases that describe the *kind* of relationship, written \
like themes rather than facts -- e.g. "supply chain concentration", "regulatory \
exposure", "competitive dynamics". These power thematic (high-level) retrieval later, so \
prefer general, reusable phrases over one-off details.
- strength: an integer 1-10 rating how central or strong this relationship is within \
this excerpt (10 = the excerpt is largely about this relationship; 1 = a passing mention).

Only extract what the text supports. It is fine to return few or no relationships for a \
chunk that doesn't describe any -- do not force connections.
"""


def extract_chunk(chunk: Chunk) -> Extraction:
    """Run one LLM extraction call for a single chunk and clean up its output.

    Cleanup is code, not prompt engineering, so it's testable without a real LLM:
    - entity names are normalized (`.strip().upper()`) so "Apple Inc." and "APPLE INC."
      merge into the same graph node later.
    - relations whose source/target isn't one of this chunk's own extracted entities are
      dropped (the model occasionally references an entity it described in prose but
      didn't emit in the `entities` list).
    """
    user = (
        f"Company: {chunk.company}\n"
        f"Section: {chunk.section}\n"
        f"Chunk ID: {chunk.id}\n\n"
        f"Text:\n{chunk.text}"
    )
    raw = llm_extract(
        system=EXTRACTION_SYSTEM_PROMPT,
        user=user,
        schema=Extraction,
        model=settings.extract_model,
    )

    entities = [
        Entity(name=e.name.strip().upper(), type=e.type, description=e.description)
        for e in raw.entities
    ]
    known_names = {e.name for e in entities}

    relations = []
    for r in raw.relations:
        source = r.source.strip().upper()
        target = r.target.strip().upper()
        if source not in known_names or target not in known_names:
            continue
        relations.append(
            Relation(
                source=source,
                target=target,
                description=r.description,
                keywords=r.keywords,
                strength=r.strength,
            )
        )

    return Extraction(entities=entities, relations=relations)


def extract_all(chunks: list[Chunk]) -> None:
    """Checkpointed batch extraction: writes one JSON line per chunk to
    data/extractions.jsonl, `{"chunk_id": ..., "extraction": {...}}`.

    Resumable: chunk ids already present in the file are skipped, so killing a
    400-chunk run at chunk 250 and re-running only pays for the remaining 150. A
    per-chunk failure is logged and skipped -- it never aborts the rest of the run
    (see PLAN.md section 6's failure-handling policy).
    """
    out_path = settings.data_dir / "extractions.jsonl"
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    done_ids: set[str] = set()
    if out_path.exists():
        with out_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    done_ids.add(json.loads(line)["chunk_id"])

    todo = [c for c in chunks if c.id not in done_ids]
    console = Console()
    console.print(f"extract: {len(done_ids)} chunks already done, {len(todo)} to go")

    total_entities = 0
    total_relations = 0
    total_cost = 0.0

    with out_path.open("a", encoding="utf-8") as f, Progress() as progress:
        task = progress.add_task("extracting", total=len(todo))
        for chunk in todo:
            try:
                # Each chunk gets its own trace (its own span tree + JSONL trace file) so
                # a single failed chunk's trace is independently inspectable.
                with span("extract_chunk", chunk_id=chunk.id) as root:
                    extraction = extract_chunk(chunk)
                total_entities += len(extraction.entities)
                total_relations += len(extraction.relations)
                total_cost += root["summary"]["cost_usd"]
                f.write(json.dumps({"chunk_id": chunk.id, "extraction": extraction.model_dump()}) + "\n")
                f.flush()
            except Exception as exc:  # noqa: BLE001 - a single bad chunk must not kill the run
                console.print(f"[red]FAILED[/red] {chunk.id}: {exc}")
            progress.advance(task)

    console.print(
        f"extract done: {total_entities} entities, {total_relations} relations, "
        f"${total_cost:.4f} spent this run"
    )


def load_extractions() -> list[tuple[str, Extraction]]:
    """Read data/extractions.jsonl back into (chunk_id, Extraction) pairs."""
    path = settings.data_dir / "extractions.jsonl"
    if not path.exists():
        return []
    results: list[tuple[str, Extraction]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                record = json.loads(line)
                results.append((record["chunk_id"], Extraction.model_validate(record["extraction"])))
    return results


def build_graph(store: GraphStore) -> None:
    """Load data/extractions.jsonl + data/chunks.jsonl and upsert everything into `store`.

    Order matters: a chunk's entities are upserted before its relations (relations
    MATCH both endpoints, see graph_store.py), and mentions are linked last (link_mention
    also expects the entity to already exist).

    NOTE: this only populates the graph store. Embedding entity descriptions into
    Chroma's `entities` collection and relation descriptions into `relations` (so
    graphrag/lightrag can vector-search them) is NOT done here -- it happens in the
    `finrag build-graph` CLI command, which needs `VectorStore` from
    `stores/vector_store.py`. That wiring is a later step; this function only knows
    about the graph store.
    """
    chunks_by_id = {c.id: c for c in load_chunks()}

    for chunk_id, extraction in load_extractions():
        chunk = chunks_by_id.get(chunk_id)
        if chunk is None:
            continue  # chunk was removed/renamed since this extraction was written
        for entity in extraction.entities:
            store.upsert_entity(entity)
        for relation in extraction.relations:
            store.upsert_relation(relation)
        for entity in extraction.entities:
            store.link_mention(entity.name, chunk)
