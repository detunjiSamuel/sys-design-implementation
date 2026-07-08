"""Phase 2 + Phase 3: embed things into Chroma. `index_chunks` builds the naive RAG index;
`index_graph` builds the two graph-retrieval indexes (`entities`, `relations`) that
graphrag/lightrag vector-search before ever touching Neo4j.
"""

from finrag.extract import load_extractions
from finrag.ingest.chunk import load_chunks
from finrag.models import Entity, Relation
from finrag.observability import span
from finrag.stores.graph_store import _DESCRIPTION_CAP, _DESCRIPTION_SEP
from finrag.stores.vector_store import VectorStore


def index_chunks() -> int:
    """Load every chunk from data/chunks.jsonl and upsert it into the "chunks" collection.

    Returns the number of chunks indexed. Idempotent: rerunning overwrites existing ids
    rather than duplicating them (VectorStore.add uses upsert).
    """
    with span("index_chunks") as record:
        chunks = load_chunks()
        store = VectorStore()
        store.add(
            collection="chunks",
            ids=[c.id for c in chunks],
            texts=[c.text for c in chunks],
            metadatas=[{"company": c.company, "section": c.section} for c in chunks],
        )
        record["attrs"]["count"] = len(chunks)
        return len(chunks)


def _merge_extractions() -> tuple[dict[str, Entity], dict[tuple[str, str], Relation]]:
    """Fold every per-chunk extraction into one entity per name and one relation per
    (source, target) pair, using the exact same concat-with-cap merge policy as
    `Neo4jGraphStore`/`FakeGraphStore` (see stores/graph_store.py) -- so the text we embed
    here matches the description that ends up on the graph node/edge, not just the first
    chunk's version of it.
    """
    entities: dict[str, Entity] = {}
    relations: dict[tuple[str, str], Relation] = {}

    for _chunk_id, extraction in load_extractions():
        for e in extraction.entities:
            existing = entities.get(e.name)
            if existing is None:
                entities[e.name] = e
            else:
                merged_desc = (existing.description + _DESCRIPTION_SEP + e.description)[:_DESCRIPTION_CAP]
                entities[e.name] = Entity(name=e.name, type=existing.type, description=merged_desc)

        for r in extraction.relations:
            key = (r.source, r.target)
            existing = relations.get(key)
            if existing is None:
                relations[key] = r
            else:
                merged_desc = (existing.description + _DESCRIPTION_SEP + r.description)[:_DESCRIPTION_CAP]
                merged_keywords = existing.keywords + [k for k in r.keywords if k not in existing.keywords]
                relations[key] = Relation(
                    source=r.source,
                    target=r.target,
                    description=merged_desc,
                    keywords=merged_keywords,
                    strength=max(existing.strength, r.strength),
                )

    return entities, relations


def index_graph() -> tuple[int, int]:
    """Embed entity + relation descriptions from data/extractions.jsonl into Chroma's
    "entities" and "relations" collections. This is the low-level/high-level index
    LightRAG's dual-level retrieval searches, and the entity-linking index GraphRAG
    seeds its neighborhood walk from.

    Doc ids double as the join key back to the graph, so a vector hit converts to a
    graph lookup with no joins (PLAN.md section 4.3):
    - entities:  id = entity name              (matches Entity.name, the Neo4j merge key)
    - relations: id = "{source}|{target}"      (matches the (source, target) edge key)

    Chroma metadata values must be scalars, so `keywords` is stored comma-joined rather
    than as a list; `retrievers/light_rag.py` splits it back out on read.

    Returns (n_entities, n_relations) embedded.
    """
    entities, relations = _merge_extractions()

    with span("index_graph") as record:
        store = VectorStore()

        entity_list = list(entities.values())
        store.add(
            collection="entities",
            ids=[e.name for e in entity_list],
            texts=[f"{e.name} ({e.type}): {e.description}" for e in entity_list],
            metadatas=[{"type": e.type} for e in entity_list],
        )

        relation_list = list(relations.values())
        store.add(
            collection="relations",
            ids=[f"{r.source}|{r.target}" for r in relation_list],
            texts=[
                f"{r.source} -> {r.target}: {r.description} | keywords: {', '.join(r.keywords)}"
                for r in relation_list
            ],
            metadatas=[
                {
                    "source": r.source,
                    "target": r.target,
                    "strength": r.strength,
                    "description": r.description,
                    "keywords": ", ".join(r.keywords),
                }
                for r in relation_list
            ],
        )

        record["attrs"]["n_entities"] = len(entity_list)
        record["attrs"]["n_relations"] = len(relation_list)
        return len(entity_list), len(relation_list)
