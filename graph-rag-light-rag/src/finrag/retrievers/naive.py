"""Naive RAG retrieval: embed the question, fetch the top-k most similar chunks. No graph,
no keyword decomposition — this is the baseline every other strategy is measured against.
"""

from finrag.config import settings
from finrag.models import Chunk, RetrievalResult
from finrag.observability import span
from finrag.stores.vector_store import VectorStore


class NaiveRetriever:
    name = "naive"

    def __init__(self, store: VectorStore | None = None) -> None:
        self._store = store or VectorStore()

    def retrieve(self, question: str) -> RetrievalResult:
        with span("retrieve", mode=self.name) as record:
            hits = self._store.query("chunks", question, settings.top_k_chunks)
            chunks = [
                Chunk(
                    id=chunk_id,
                    company=meta.get("company", ""),
                    section=meta.get("section", ""),
                    text=text,
                )
                for chunk_id, text, meta, _score in hits
            ]
            record["attrs"]["k"] = len(chunks)
            return RetrievalResult(chunks=chunks, entities=[], relations=[])
