"""FakeGraphStore tests: upserts, BFS neighborhood at different hop counts,
chunks_for_entities dedupe/limit, and description concat-with-cap on merge collisions.
"""

from finrag.models import Chunk, Entity, Relation
from finrag.stores.graph_store import _DESCRIPTION_CAP, _DESCRIPTION_SEP, FakeGraphStore


def _entity(name: str, desc: str = "d") -> Entity:
    return Entity(name=name, type="COMPANY", description=desc)


def _relation(source: str, target: str) -> Relation:
    return Relation(
        source=source,
        target=target,
        description=f"{source} relates to {target}.",
        keywords=["k"],
        strength=5,
    )


def test_neighborhood_one_hop_excludes_two_hop_entity() -> None:
    # A -- B -- C path graph.
    store = FakeGraphStore()
    for name in ("A", "B", "C"):
        store.upsert_entity(_entity(name))
    store.upsert_relation(_relation("A", "B"))
    store.upsert_relation(_relation("B", "C"))

    entities, relations = store.neighborhood(["A"], hops=1)

    names = {e.name for e in entities}
    assert names == {"A", "B"}
    assert "C" not in names
    assert len(relations) == 1
    assert (relations[0].source, relations[0].target) == ("A", "B")


def test_neighborhood_two_hops_reaches_far_entity() -> None:
    store = FakeGraphStore()
    for name in ("A", "B", "C"):
        store.upsert_entity(_entity(name))
    store.upsert_relation(_relation("A", "B"))
    store.upsert_relation(_relation("B", "C"))

    entities, relations = store.neighborhood(["A"], hops=2)

    assert {e.name for e in entities} == {"A", "B", "C"}
    assert len(relations) == 2


def test_neighborhood_includes_isolated_seed_with_no_relations() -> None:
    store = FakeGraphStore()
    store.upsert_entity(_entity("LONELY"))

    entities, relations = store.neighborhood(["LONELY"], hops=1)

    assert [e.name for e in entities] == ["LONELY"]
    assert relations == []


def test_chunks_for_entities_dedupes_and_limits() -> None:
    store = FakeGraphStore()
    store.upsert_entity(_entity("APPLE"))
    store.upsert_entity(_entity("TSMC"))
    c1 = Chunk(id="c1", company="AAPL", section="item1a", text="t1")
    c2 = Chunk(id="c2", company="AAPL", section="item1a", text="t2")
    store.link_mention("APPLE", c1)
    store.link_mention("TSMC", c1)  # same chunk mentioned by two entities -> deduped
    store.link_mention("APPLE", c2)

    result = store.chunks_for_entities(["APPLE", "TSMC"], limit=10)
    assert [c.id for c in result] == ["c1", "c2"]

    limited = store.chunks_for_entities(["APPLE", "TSMC"], limit=1)
    assert len(limited) == 1


def test_entity_description_concat_on_double_upsert() -> None:
    store = FakeGraphStore()
    store.upsert_entity(_entity("APPLE", desc="First description."))
    store.upsert_entity(_entity("APPLE", desc="Second description."))

    entities, _ = store.neighborhood(["APPLE"], hops=1)
    merged = next(e for e in entities if e.name == "APPLE")
    assert merged.description == "First description." + _DESCRIPTION_SEP + "Second description."


def test_entity_description_is_capped() -> None:
    store = FakeGraphStore()
    store.upsert_entity(_entity("X", desc="A" * 3000))
    store.upsert_entity(_entity("X", desc="B" * 3000))

    entities, _ = store.neighborhood(["X"], hops=1)
    merged = next(e for e in entities if e.name == "X")
    assert len(merged.description) == _DESCRIPTION_CAP


def test_clear_removes_everything() -> None:
    store = FakeGraphStore()
    store.upsert_entity(_entity("APPLE"))
    store.link_mention("APPLE", Chunk(id="c1", company="AAPL", section="item1", text="t"))

    store.clear()

    entities, relations = store.neighborhood(["APPLE"], hops=1)
    assert entities == []
    assert relations == []
    assert store.chunks_for_entities(["APPLE"], limit=10) == []
