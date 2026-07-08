"""Roundtrip tests for the shared Pydantic models (models.py)."""

from finrag.models import (
    Answer,
    Chunk,
    Entity,
    Extraction,
    QueryKeywords,
    Relation,
    RetrievalResult,
)


def test_chunk_roundtrip() -> None:
    chunk = Chunk(id="AAPL_item1a_000", company="AAPL", section="item1a", text="Risk text.")
    restored = Chunk.model_validate_json(chunk.model_dump_json())
    assert restored == chunk


def test_entity_roundtrip() -> None:
    entity = Entity(name="APPLE INC", type="COMPANY", description="Consumer electronics maker.")
    restored = Entity.model_validate_json(entity.model_dump_json())
    assert restored == entity


def test_relation_roundtrip() -> None:
    relation = Relation(
        source="APPLE INC",
        target="TSMC",
        description="Apple depends on TSMC for chip fabrication.",
        keywords=["supply chain", "semiconductors"],
        strength=8,
    )
    restored = Relation.model_validate_json(relation.model_dump_json())
    assert restored == relation
    assert 1 <= relation.strength <= 10


def test_extraction_roundtrip() -> None:
    extraction = Extraction(
        entities=[Entity(name="APPLE INC", type="COMPANY", description="d")],
        relations=[
            Relation(source="A", target="B", description="d", keywords=["k"], strength=5)
        ],
    )
    restored = Extraction.model_validate_json(extraction.model_dump_json())
    assert restored == extraction


def test_query_keywords_roundtrip() -> None:
    kw = QueryKeywords(low_level=["Apple", "TSMC"], high_level=["supply chain concentration"])
    restored = QueryKeywords.model_validate_json(kw.model_dump_json())
    assert restored == kw


def test_retrieval_result_roundtrip() -> None:
    result = RetrievalResult(
        chunks=[Chunk(id="c1", company="AAPL", section="item1", text="t")],
        entities=[Entity(name="APPLE INC", type="COMPANY", description="d")],
        relations=[],
    )
    restored = RetrievalResult.model_validate_json(result.model_dump_json())
    assert restored == result


def test_answer_roundtrip() -> None:
    answer = Answer(text="Apple faces supply chain risk.", citations=["AAPL_item1a_000"], mode="naive")
    restored = Answer.model_validate_json(answer.model_dump_json())
    assert restored == answer
