"""Chroma wrapper: one persistent client, three collections (chunks/entities/relations).

We compute embeddings ourselves via `finrag.embeddings.embed` and pass them explicitly to
Chroma instead of letting Chroma manage an embedding function — that keeps "what model
produced this vector" answerable from one file (embeddings.py) instead of split across two
systems. This class is generic over the collection name; callers (index.py, extract/graph
building, the retrievers) decide which of the three collections they're writing to.
"""

from finrag.config import settings
from finrag.embeddings import embed

_BATCH_SIZE = 100


class VectorStore:
    """Thin wrapper around a single `chromadb.PersistentClient` rooted at data/chroma."""

    def __init__(self) -> None:
        import chromadb

        self._client = chromadb.PersistentClient(path=str(settings.data_dir / "chroma"))

    def _get_or_create_collection(self, collection: str):
        # Cosine distance so `1 - distance` below is a well-defined similarity in [0, 1]
        # for normalized embeddings (bge-small, like most sentence embedders, is normalized).
        return self._client.get_or_create_collection(
            collection, metadata={"hnsw:space": "cosine"}
        )

    def add(
        self,
        collection: str,
        ids: list[str],
        texts: list[str],
        metadatas: list[dict],
    ) -> None:
        """Embed `texts` and upsert them into `collection`, batched by ~100.

        `upsert` (not `add`) so re-running indexing/extraction on the same ids is
        idempotent: it overwrites rather than erroring on duplicate ids.
        """
        col = self._get_or_create_collection(collection)
        for start in range(0, len(ids), _BATCH_SIZE):
            end = start + _BATCH_SIZE
            batch_ids = ids[start:end]
            batch_texts = texts[start:end]
            batch_metadatas = metadatas[start:end]
            batch_embeddings = embed(batch_texts)
            col.upsert(
                ids=batch_ids,
                embeddings=batch_embeddings,
                documents=batch_texts,
                metadatas=batch_metadatas,
            )

    def query(self, collection: str, text: str, k: int) -> list[tuple[str, str, dict, float]]:
        """Embed `text` and return the top-k nearest neighbors in `collection` as
        (id, text, metadata, similarity_score) tuples, best match first.
        """
        col = self._get_or_create_collection(collection)
        [query_embedding] = embed([text])
        result = col.query(query_embeddings=[query_embedding], n_results=k)

        ids = result["ids"][0]
        documents = result["documents"][0]
        metadatas = result["metadatas"][0]
        distances = result["distances"][0]

        return [
            (id_, doc, meta, 1.0 - dist)
            for id_, doc, meta, dist in zip(ids, documents, metadatas, distances)
        ]
