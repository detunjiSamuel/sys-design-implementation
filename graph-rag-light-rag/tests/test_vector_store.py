"""vector_store.py tests: fake embeddings (deterministic, no model download), tmp chroma dir
(conftest already redirects settings.data_dir per test).
"""

import hashlib

from finrag.stores import vector_store as vector_store_module
from finrag.stores.vector_store import VectorStore


def _fake_embed(texts: list[str]) -> list[list[float]]:
    """Deterministic 8-dim vector per text, derived from its hash. Different texts get
    (almost certainly) different vectors; identical texts get identical vectors.
    """
    vectors = []
    for text in texts:
        digest = hashlib.md5(text.encode()).digest()
        vectors.append([b / 255.0 for b in digest[:8]])
    return vectors


def _patch_embed(monkeypatch) -> None:
    monkeypatch.setattr(vector_store_module, "embed", _fake_embed)


def test_add_and_query_roundtrip(monkeypatch) -> None:
    _patch_embed(monkeypatch)
    store = VectorStore()

    ids = ["a", "b", "c"]
    texts = [
        "Apple faces supply chain risk from concentration in Asia.",
        "JPMorgan discusses interest rate risk.",
        "NVIDIA depends on TSMC for chip fabrication.",
    ]
    metadatas = [{"company": "AAPL"}, {"company": "JPM"}, {"company": "NVDA"}]

    store.add("chunks", ids, texts, metadatas)
    results = store.query("chunks", texts[0], k=3)

    assert len(results) == 3
    result_ids = [r[0] for r in results]
    assert set(result_ids) == set(ids)
    # Querying with the exact text of "a" should put "a" first (distance ~0, score ~1).
    assert result_ids[0] == "a"

    top_id, top_text, top_meta, top_score = results[0]
    assert top_text == texts[0]
    assert top_meta == {"company": "AAPL"}
    assert top_score > 0.99


def test_query_k_limits_results(monkeypatch) -> None:
    _patch_embed(monkeypatch)
    store = VectorStore()
    ids = [f"c{i}" for i in range(5)]
    texts = [f"chunk number {i} about risk factors" for i in range(5)]
    metadatas = [{"company": "AAPL"} for _ in range(5)]

    store.add("chunks", ids, texts, metadatas)
    results = store.query("chunks", "risk factors", k=2)

    assert len(results) == 2


def test_upsert_is_idempotent(monkeypatch) -> None:
    _patch_embed(monkeypatch)
    store = VectorStore()
    ids = ["a", "b"]
    texts = ["first chunk text", "second chunk text"]
    metadatas = [{"company": "AAPL"}, {"company": "AAPL"}]

    store.add("chunks", ids, texts, metadatas)
    store.add("chunks", ids, texts, metadatas)  # re-add the same ids

    col = store._get_or_create_collection("chunks")
    assert col.count() == 2


def test_add_batches_across_collection_boundary(monkeypatch) -> None:
    _patch_embed(monkeypatch)
    store = VectorStore()
    n = 250  # forces 3 batches at _BATCH_SIZE=100
    ids = [f"c{i}" for i in range(n)]
    texts = [f"text {i}" for i in range(n)]
    metadatas = [{"company": "AAPL"} for _ in range(n)]

    store.add("chunks", ids, texts, metadatas)

    col = store._get_or_create_collection("chunks")
    assert col.count() == n
