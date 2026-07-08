"""light_rag.py tests: fake `QueryKeywords` from llm.extract (no network), fake entity/
relation vector docs, FakeGraphStore. Checks that both dual-level branches contribute to
the union, that the union is deduped, and that a "relations" collection hit's "SRC|DST"
doc id round-trips back into the same Relation fields via metadata.
"""

import hashlib

from finrag.config import settings
from finrag.models import Chunk, Entity, QueryKeywords, Relation
from finrag.retrievers import light_rag as light_rag_module
from finrag.retrievers.light_rag import MAX_RELATIONS, LightRAGRetriever
from finrag.stores import vector_store as vector_store_module
from finrag.stores.graph_store import FakeGraphStore
from finrag.stores.vector_store import VectorStore


def _fake_embed(texts: list[str]) -> list[list[float]]:
    vectors = []
    for text in texts:
        digest = hashlib.md5(text.encode()).digest()
        vectors.append([b / 255.0 for b in digest[:8]])
    return vectors


def _entity(name: str, desc: str = "d") -> Entity:
    return Entity(name=name, type="COMPANY", description=desc)


def _relation(source: str, target: str, strength: int = 5, keywords=None) -> Relation:
    return Relation(
        source=source, target=target, description=f"{source} relates to {target}.",
        keywords=keywords or ["k"], strength=strength,
    )


def _relation_metadata(r: Relation) -> dict:
    return {
        "source": r.source,
        "target": r.target,
        "strength": r.strength,
        "description": r.description,
        "keywords": ", ".join(r.keywords),
    }


def _build_store(monkeypatch) -> VectorStore:
    monkeypatch.setattr(vector_store_module, "embed", _fake_embed)
    store = VectorStore()

    # "entities": a single doc, so the low-level keyword "Apple" deterministically hits it.
    store.add(
        "entities", ["APPLE"], ["APPLE (COMPANY): Maker of iPhones."], [{"type": "COMPANY"}]
    )

    # "relations": a single doc, so the high-level keyword deterministically hits it.
    # Metadata mirrors exactly what finrag.index.index_graph() writes.
    relation = _relation("NVIDIA", "QUALCOMM", strength=6, keywords=["regulatory exposure", "licensing"])
    store.add(
        "relations",
        [f"{relation.source}|{relation.target}"],
        [f"{relation.source} -> {relation.target}: {relation.description}"],
        [_relation_metadata(relation)],
    )
    return store


def _build_graph() -> FakeGraphStore:
    graph = FakeGraphStore()
    for name in ("APPLE", "TSMC", "NVIDIA", "QUALCOMM"):
        graph.upsert_entity(_entity(name))
    graph.upsert_relation(_relation("APPLE", "TSMC", strength=8))

    c1 = Chunk(id="AAPL_item1a_000", company="AAPL", section="item1a", text="Apple depends on TSMC.")
    c2 = Chunk(id="NVDA_item1a_000", company="NVDA", section="item1a", text="NVIDIA and Qualcomm face regulation.")
    graph.link_mention("APPLE", c1)
    graph.link_mention("TSMC", c1)
    graph.link_mention("NVIDIA", c2)
    graph.link_mention("QUALCOMM", c2)
    return graph


def _patch_keywords(monkeypatch, low_level: list[str], high_level: list[str]) -> None:
    monkeypatch.setattr(
        light_rag_module,
        "llm_extract",
        lambda **kwargs: QueryKeywords(low_level=low_level, high_level=high_level),
    )


def test_low_and_high_branches_both_contribute(monkeypatch) -> None:
    store = _build_store(monkeypatch)
    graph = _build_graph()
    _patch_keywords(monkeypatch, low_level=["Apple"], high_level=["regulatory exposure"])
    monkeypatch.setattr(settings, "top_k_chunks", 10)

    retriever = LightRAGRetriever(vector_store=store, graph_store=graph)
    result = retriever.retrieve("How are Apple's suppliers regulated compared to NVIDIA's?")

    names = {e.name for e in result.entities}
    # low-level ("Apple") -> APPLE seed -> one-hop neighborhood -> TSMC too.
    assert {"APPLE", "TSMC"} <= names
    # high-level ("regulatory exposure") -> the NVIDIA-QUALCOMM relation doc -> its endpoints.
    assert {"NVIDIA", "QUALCOMM"} <= names

    rel_pairs = {(r.source, r.target) for r in result.relations}
    assert ("APPLE", "TSMC") in rel_pairs
    assert ("NVIDIA", "QUALCOMM") in rel_pairs

    chunk_ids = {c.id for c in result.chunks}
    assert "AAPL_item1a_000" in chunk_ids
    assert "NVDA_item1a_000" in chunk_ids


def test_relations_collection_id_round_trips_to_relation_model(monkeypatch) -> None:
    store = _build_store(monkeypatch)
    graph = _build_graph()

    # Confirm the "SRC|DST" convention directly on the store first.
    hits = store.query("relations", "regulatory exposure", k=1)
    hit_id, _text, meta, _score = hits[0]
    assert hit_id == "NVIDIA|QUALCOMM"
    assert hit_id.split("|") == [meta["source"], meta["target"]]

    _patch_keywords(monkeypatch, low_level=[], high_level=["regulatory exposure"])
    monkeypatch.setattr(settings, "top_k_chunks", 10)

    retriever = LightRAGRetriever(vector_store=store, graph_store=graph)
    result = retriever.retrieve("What regulatory risk connects NVIDIA and Qualcomm?")

    relation = next(r for r in result.relations if r.source == "NVIDIA" and r.target == "QUALCOMM")
    assert relation.strength == 6
    assert relation.keywords == ["regulatory exposure", "licensing"]


def test_dedupe_when_entities_overlap_across_branches(monkeypatch) -> None:
    store = _build_store(monkeypatch)
    graph = _build_graph()
    _patch_keywords(monkeypatch, low_level=["Apple"], high_level=["regulatory exposure"])
    monkeypatch.setattr(settings, "top_k_chunks", 10)

    retriever = LightRAGRetriever(vector_store=store, graph_store=graph)
    result = retriever.retrieve("question")

    names = [e.name for e in result.entities]
    assert len(names) == len(set(names))  # no duplicate entities despite two branches

    pairs = [(r.source, r.target) for r in result.relations]
    assert len(pairs) == len(set(pairs))  # no duplicate relations either


def test_relations_capped_at_max(monkeypatch) -> None:
    monkeypatch.setattr(vector_store_module, "embed", _fake_embed)
    store = VectorStore()
    store.add("entities", ["HUB"], ["HUB (COMPANY): central entity."], [{"type": "COMPANY"}])

    ids, texts, metas = [], [], []
    for i in range(30):
        r = _relation("HUB", f"LEAF{i}", strength=(i % 10) + 1, keywords=["theme"])
        ids.append(f"{r.source}|{r.target}")
        texts.append(f"{r.source} -> {r.target}: {r.description}")
        metas.append(_relation_metadata(r))
    store.add("relations", ids, texts, metas)

    graph = FakeGraphStore()
    graph.upsert_entity(_entity("HUB"))
    for i in range(30):
        graph.upsert_entity(_entity(f"LEAF{i}"))

    monkeypatch.setattr(
        light_rag_module, "llm_extract", lambda **kwargs: QueryKeywords(low_level=[], high_level=["theme"])
    )
    # k=30 so the single high-level keyword can surface every doc in the collection.
    monkeypatch.setattr(light_rag_module, "KEYWORDS_PER_QUERY", 30)
    monkeypatch.setattr(settings, "top_k_chunks", 10)

    retriever = LightRAGRetriever(vector_store=store, graph_store=graph)
    result = retriever.retrieve("question")

    assert len(result.relations) == MAX_RELATIONS
    strengths = [r.strength for r in result.relations]
    assert strengths == sorted(strengths, reverse=True)


def test_retriever_name() -> None:
    assert LightRAGRetriever.name == "lightrag"
