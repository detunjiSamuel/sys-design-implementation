"""LightRAG-style dual-level retrieval (PLAN.md section 2, method 1).

An LLM splits the question into *low-level* keywords (concrete entities: "Apple", "TSMC")
and *high-level* keywords (themes: "supply chain concentration"). Low-level keywords
search Chroma's `entities` collection and expand one hop in the graph -- the local view.
High-level keywords search Chroma's `relations` collection directly -- relationship
descriptions written at extraction time *are* the thematic index, so there is no
community-summarization step to build or maintain (PLAN.md's LightRAG pitch). The union
of both views, deduped and capped, becomes the context.
"""

from finrag.config import settings
from finrag.llm import extract as llm_extract
from finrag.models import Entity, QueryKeywords, Relation, RetrievalResult
from finrag.observability import span
from finrag.stores.graph_store import GraphStore, Neo4jGraphStore
from finrag.stores.vector_store import VectorStore

MAX_RELATIONS = 20
KEYWORDS_PER_QUERY = 3  # k for each individual keyword's vector search

KEYWORD_SYSTEM_PROMPT = """\
You are preparing a question about SEC 10-K filings for dual-level graph retrieval. \
Split the question into two keyword lists:

- low_level: concrete entity mentions in the question -- company names, people, \
products, specific regulations -- things you'd expect to find as a single node in a \
knowledge graph, e.g. "Apple", "TSMC", "iPhone".
- high_level: thematic or conceptual terms the question is really about -- things you'd \
expect to find in a relationship description, e.g. "supply chain concentration", \
"interest rate risk", "regulatory exposure".

Keep each list short (1-5 items). It is fine for one list to be empty if the question is \
purely local (e.g. "What was NVIDIA's data center revenue driver?") or purely thematic \
(e.g. "What macroeconomic risks recur across companies?").
"""


class LightRAGRetriever:
    name = "lightrag"

    def __init__(
        self,
        vector_store: VectorStore | None = None,
        graph_store: GraphStore | None = None,
    ) -> None:
        self._vector_store = vector_store or VectorStore()
        self._graph_store = graph_store or Neo4jGraphStore()

    def _low_level(self, keywords: list[str]) -> tuple[list[str], list[Entity], list[Relation]]:
        """Local view: each low-level keyword seeds an entity search, then one graph hop."""
        seed_names: list[str] = []
        for keyword in keywords:
            hits = self._vector_store.query("entities", keyword, KEYWORDS_PER_QUERY)
            for name, _text, _meta, _score in hits:
                if name not in seed_names:
                    seed_names.append(name)

        if not seed_names:
            return [], [], []
        entities, relations = self._graph_store.neighborhood(seed_names, hops=1)
        return seed_names, entities, relations

    def _high_level(self, keywords: list[str]) -> tuple[list[Entity], list[Relation]]:
        """Global view: each high-level keyword searches relation *descriptions* directly.

        Chroma's `relations` collection doc id is "{source}|{target}" (see
        `finrag.index.index_graph`) and its metadata carries the full relation fields, so a
        hit reconstructs into a `Relation` straight from metadata -- no graph round-trip
        needed just to get the edge itself.
        """
        relations: dict[tuple[str, str], Relation] = {}
        endpoint_names: set[str] = set()
        for keyword in keywords:
            hits = self._vector_store.query("relations", keyword, KEYWORDS_PER_QUERY)
            for _doc_id, _text, meta, _score in hits:
                keyword_list = [k.strip() for k in meta.get("keywords", "").split(",") if k.strip()]
                relation = Relation(
                    source=meta["source"],
                    target=meta["target"],
                    description=meta["description"],
                    keywords=keyword_list,
                    strength=meta["strength"],
                )
                relations[(relation.source, relation.target)] = relation
                endpoint_names.add(relation.source)
                endpoint_names.add(relation.target)

        entities: list[Entity] = []
        if endpoint_names:
            # hops=0: we only want the endpoint nodes' own records (type/description), not
            # a further walk. FakeGraphStore honors hops=0 exactly; Neo4jGraphStore floors
            # hops at 1, so a live run may also surface the endpoints' immediate neighbors
            # -- harmless extra context, capped later along with everything else.
            fetched_entities, _fetched_relations = self._graph_store.neighborhood(
                list(endpoint_names), hops=0
            )
            entities = [e for e in fetched_entities if e.name in endpoint_names]

        return entities, list(relations.values())

    def retrieve(self, question: str) -> RetrievalResult:
        with span("retrieve", mode=self.name) as record:
            keywords = llm_extract(
                system=KEYWORD_SYSTEM_PROMPT,
                user=question,
                schema=QueryKeywords,
            )

            low_seeds, low_entities, low_relations = self._low_level(keywords.low_level)
            high_entities, high_relations = self._high_level(keywords.high_level)

            # Union + dedupe. Later entries win on collision, which is fine here since
            # low/high views describing the same node should mostly agree.
            entities_by_name: dict[str, Entity] = {e.name: e for e in low_entities + high_entities}
            relations_by_key: dict[tuple[str, str], Relation] = {
                (r.source, r.target): r for r in low_relations + high_relations
            }
            relations = sorted(relations_by_key.values(), key=lambda r: r.strength, reverse=True)[
                :MAX_RELATIONS
            ]
            entities = list(entities_by_name.values())

            all_names = list(dict.fromkeys(low_seeds + [e.name for e in entities]))
            chunks = (
                self._graph_store.chunks_for_entities(all_names, limit=settings.top_k_chunks)
                if all_names
                else []
            )

            record["attrs"]["low_level_keywords"] = keywords.low_level
            record["attrs"]["high_level_keywords"] = keywords.high_level
            record["attrs"]["n_entities"] = len(entities)
            record["attrs"]["n_relations"] = len(relations)

            return RetrievalResult(chunks=chunks, entities=entities, relations=relations)
