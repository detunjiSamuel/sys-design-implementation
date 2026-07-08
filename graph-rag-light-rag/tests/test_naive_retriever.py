"""naive.py tests: seed fake chunks through the store (fake embeddings, no model download),
check RetrievalResult shape and that k is respected.
"""

import hashlib

from finrag.config import settings
from finrag.retrievers.naive import NaiveRetriever
from finrag.stores import vector_store as vector_store_module
from finrag.stores.vector_store import VectorStore


def _fake_embed(texts: list[str]) -> list[list[float]]:
    vectors = []
    for text in texts:
        digest = hashlib.md5(text.encode()).digest()
        vectors.append([b / 255.0 for b in digest[:8]])
    return vectors


def _seed_store(monkeypatch) -> VectorStore:
    monkeypatch.setattr(vector_store_module, "embed", _fake_embed)
    store = VectorStore()
    ids = ["AAPL_item1a_000", "AAPL_item1a_001", "JPM_item1a_000"]
    texts = [
        "Apple faces significant risk from supply chain concentration in Asia.",
        "The Company's products depend on custom components from limited sources.",
        "JPMorgan is exposed to interest rate risk across its loan portfolio.",
    ]
    metadatas = [
        {"company": "AAPL", "section": "item1a"},
        {"company": "AAPL", "section": "item1a"},
        {"company": "JPM", "section": "item1a"},
    ]
    store.add("chunks", ids, texts, metadatas)
    return store


def test_retrieve_returns_chunks_only(monkeypatch) -> None:
    store = _seed_store(monkeypatch)
    monkeypatch.setattr(settings, "top_k_chunks", 2)

    retriever = NaiveRetriever(store=store)
    result = retriever.retrieve("supply chain risk in Asia")

    assert len(result.chunks) == 2
    assert result.entities == []
    assert result.relations == []
    for chunk in result.chunks:
        assert chunk.id
        assert chunk.company
        assert chunk.section
        assert chunk.text


def test_retrieve_respects_top_k(monkeypatch) -> None:
    store = _seed_store(monkeypatch)
    monkeypatch.setattr(settings, "top_k_chunks", 1)

    retriever = NaiveRetriever(store=store)
    result = retriever.retrieve("interest rate risk")

    assert len(result.chunks) == 1


def test_retriever_name() -> None:
    assert NaiveRetriever.name == "naive"
