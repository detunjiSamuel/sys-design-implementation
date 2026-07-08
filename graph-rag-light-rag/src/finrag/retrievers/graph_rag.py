"""GraphRAG retrieval: link the question to seed entities via vector search, expand the
graph neighborhood k hops out, and pull the chunks those entities were mentioned in.

This is the "pre-computed connections" strategy from PLAN.md section 2: instead of hoping
a single chunk is similar enough to the whole question (naive RAG's failure mode on
multi-hop questions), we let the knowledge graph built at ingest time do the multi-hop
reasoning, and hand the generator the connected entities/relations plus their sources.
"""

from finrag.config import settings
from finrag.models import RetrievalResult
from finrag.observability import span
from finrag.stores.graph_store import GraphStore, Neo4jGraphStore
from finrag.stores.vector_store import VectorStore

# A big neighborhood can return far more edges than fit in the context budget; keep only
# the strongest ones (Relation.strength is the LLM's own 1-10 centrality rating).
MAX_RELATIONS = 20


class GraphRAGRetriever:
    name = "graphrag"

    def __init__(
        self,
        vector_store: VectorStore | None = None,
        graph_store: GraphStore | None = None,
    ) -> None:
        self._vector_store = vector_store or VectorStore()
        self._graph_store = graph_store or Neo4jGraphStore()

    def retrieve(self, question: str) -> RetrievalResult:
        with span("retrieve", mode=self.name) as record:
            # 1. Entity linking: which graph nodes does the question seem to be about?
            hits = self._vector_store.query("entities", question, settings.top_k_entities)
            seed_names = [entity_name for entity_name, _text, _meta, _score in hits]

            # 2. k-hop expansion: walk out from the seeds to pull in connected structure
            # (this is the step naive RAG has no equivalent of).
            entities, relations = self._graph_store.neighborhood(seed_names, hops=settings.hops)
            relations = sorted(relations, key=lambda r: r.strength, reverse=True)[:MAX_RELATIONS]

            # 3. Source chunks for everything involved: the seeds themselves (in case the
            # neighborhood walk found no relations at all) plus every entity it reached.
            all_names = list(dict.fromkeys(seed_names + [e.name for e in entities]))
            chunks = (
                self._graph_store.chunks_for_entities(all_names, limit=settings.top_k_chunks)
                if all_names
                else []
            )

            record["attrs"]["n_seeds"] = len(seed_names)
            record["attrs"]["n_entities"] = len(entities)
            record["attrs"]["n_relations"] = len(relations)

            return RetrievalResult(chunks=chunks, entities=entities, relations=relations)
