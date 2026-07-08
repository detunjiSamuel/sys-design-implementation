"""graph_rag.py tests: a real VectorStore (Chroma) with fake embeddings seeded with a
single "entities" doc so entity linking is deterministic, plus a FakeGraphStore seeded
with a small graph. Checks the seed -> neighborhood -> chunks flow and that relations are
ranked by strength and capped.
"""

import hashlib

from finrag.config import settings
from finrag.models import Chunk, Entity, Relation
from finrag.retrievers.graph_rag import MAX_RELATIONS, GraphRAGRetriever
from finrag.stores import vector_store as vector_store_module
from finrag.stores.graph_store import FakeGraphStore
from finrag.stores.vector_store import VectorStore


def _fake_embed(texts: list[str]) -> list[list[float]]:
    vectors = []
    for text in texts:
        digest = hashlib.md5(text.encode()).digest()
        vectors.append([b / 255.0 for b in digest[:8]])
    return vectors


def _entity_store(monkeypatch, docs: list[tuple[str, str]]) -> VectorStore:
    monkeypatch.setattr(vector_store_module, "embed", _fake_embed)
    store = VectorStore()
    ids = [name for name, _ in docs]
    texts = [text for _, text in docs]
    metadatas = [{"type": "COMPANY"} for _ in docs]
    store.add("entities", ids, texts, metadatas)
    return store


def _entity(name: str, desc: str = "d") -> Entity:
    return Entity(name=name, type="COMPANY", description=desc)


def _relation(source: str, target: str, strength: int = 5) -> Relation:
    return Relation(
        source=source, target=target, description=f"{source} relates to {target}.",
        keywords=["k"], strength=strength,
    )


def test_seed_to_neighborhood_to_chunks(monkeypatch) -> None:
    graph = FakeGraphStore()
    for name in ("APPLE", "TSMC", "NVIDIA"):
        graph.upsert_entity(_entity(name))
    graph.upsert_relation(_relation("APPLE", "TSMC", strength=8))
    graph.upsert_relation(_relation("NVIDIA", "TSMC", strength=7))

    chunk = Chunk(id="AAPL_item1a_000", company="AAPL", section="item1a", text="Apple depends on TSMC.")
    graph.link_mention("APPLE", chunk)
    graph.link_mention("TSMC", chunk)

    # Only one doc in "entities" -> with top_k_entities=1, entity linking deterministically
    # returns APPLE regardless of how good the fake embedding's similarity math is.
    vector_store = _entity_store(monkeypatch, [("APPLE", "Apple Inc, maker of iPhones.")])
    monkeypatch.setattr(settings, "top_k_entities", 1)
    monkeypatch.setattr(settings, "hops", 2)
    monkeypatch.setattr(settings, "top_k_chunks", 10)

    retriever = GraphRAGRetriever(vector_store=vector_store, graph_store=graph)
    result = retriever.retrieve("How is Apple connected to chip suppliers?")

    names = {e.name for e in result.entities}
    assert "APPLE" in names
    assert "TSMC" in names
    assert "NVIDIA" in names  # 2 hops out from APPLE, via TSMC
    assert any(r.source == "APPLE" and r.target == "TSMC" for r in result.relations)
    assert result.chunks and result.chunks[0].id == "AAPL_item1a_000"


def test_relations_are_ranked_by_strength_and_capped(monkeypatch) -> None:
    graph = FakeGraphStore()
    graph.upsert_entity(_entity("HUB"))
    for i in range(30):
        name = f"LEAF{i}"
        graph.upsert_entity(_entity(name))
        graph.upsert_relation(_relation("HUB", name, strength=(i % 10) + 1))

    vector_store = _entity_store(monkeypatch, [("HUB", "The hub entity.")])
    monkeypatch.setattr(settings, "top_k_entities", 1)
    monkeypatch.setattr(settings, "hops", 1)
    monkeypatch.setattr(settings, "top_k_chunks", 10)

    retriever = GraphRAGRetriever(vector_store=vector_store, graph_store=graph)
    result = retriever.retrieve("hub question")

    assert len(result.relations) == MAX_RELATIONS
    strengths = [r.strength for r in result.relations]
    assert strengths == sorted(strengths, reverse=True)


def test_retriever_name() -> None:
    assert GraphRAGRetriever.name == "graphrag"
