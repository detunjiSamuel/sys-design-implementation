"""answer.py tests: fake llm.complete, no network. Checks context assembly, citation
parsing, and that an empty RetrievalResult still produces an Answer instead of raising.
"""

from finrag import answer as answer_module
from finrag.answer import generate
from finrag.models import Chunk, Entity, Relation, RetrievalResult


def _fake_complete_factory(response_text: str):
    calls = []

    def fake_complete(system: str, user: str, model: str | None = None) -> str:
        calls.append({"system": system, "user": user, "model": model})
        return response_text

    return fake_complete, calls


def test_generate_parses_known_citations(monkeypatch) -> None:
    fake_complete, calls = _fake_complete_factory(
        "Apple flags supply chain concentration risk [AAPL_item1a_002]."
    )
    monkeypatch.setattr(answer_module, "complete", fake_complete)

    result = RetrievalResult(
        chunks=[
            Chunk(id="AAPL_item1a_002", company="AAPL", section="item1a", text="Supply chain risk text."),
            Chunk(id="AAPL_item1a_003", company="AAPL", section="item1a", text="Unrelated text."),
        ],
        entities=[],
        relations=[],
    )

    ans = generate("What does Apple say about supply chain risk?", result, mode="naive")

    assert ans.mode == "naive"
    assert ans.citations == ["AAPL_item1a_002"]
    assert "Supply chain risk text." in calls[0]["user"]
    assert "[AAPL_item1a_002]" in calls[0]["user"]


def test_generate_ignores_unknown_citation_ids(monkeypatch) -> None:
    fake_complete, _ = _fake_complete_factory("See [NOT_A_REAL_CHUNK] for details.")
    monkeypatch.setattr(answer_module, "complete", fake_complete)

    result = RetrievalResult(
        chunks=[Chunk(id="AAPL_item1a_002", company="AAPL", section="item1a", text="text")],
        entities=[],
        relations=[],
    )

    ans = generate("question", result, mode="naive")

    assert ans.citations == []


def test_generate_handles_empty_result_without_raising(monkeypatch) -> None:
    fake_complete, calls = _fake_complete_factory(
        "The provided context does not contain enough information to answer this question."
    )
    monkeypatch.setattr(answer_module, "complete", fake_complete)

    result = RetrievalResult(chunks=[], entities=[], relations=[])
    ans = generate("What risks do Apple and JPMorgan share?", result, mode="naive")

    assert ans.citations == []
    assert "does not contain enough information" in ans.text
    assert "SOURCE CHUNKS" in calls[0]["user"]


def test_generate_includes_entity_and_relation_sections_when_present(monkeypatch) -> None:
    fake_complete, calls = _fake_complete_factory("Answer with [AAPL_item1a_002].")
    monkeypatch.setattr(answer_module, "complete", fake_complete)

    result = RetrievalResult(
        chunks=[Chunk(id="AAPL_item1a_002", company="AAPL", section="item1a", text="text")],
        entities=[Entity(name="Apple", type="COMPANY", description="Consumer electronics company.")],
        relations=[
            Relation(
                source="Apple",
                target="TSMC",
                description="Apple depends on TSMC for chip fabrication.",
                keywords=["supply chain"],
                strength=8,
            )
        ],
    )

    generate("question", result, mode="lightrag")

    user_prompt = calls[0]["user"]
    assert "ENTITIES:" in user_prompt
    assert "RELATIONSHIPS:" in user_prompt
    assert "Apple" in user_prompt
    assert "TSMC" in user_prompt


def test_generate_omits_entity_and_relation_sections_when_empty(monkeypatch) -> None:
    fake_complete, calls = _fake_complete_factory("Answer.")
    monkeypatch.setattr(answer_module, "complete", fake_complete)

    result = RetrievalResult(
        chunks=[Chunk(id="AAPL_item1a_002", company="AAPL", section="item1a", text="text")],
        entities=[],
        relations=[],
    )

    generate("question", result, mode="naive")

    user_prompt = calls[0]["user"]
    assert "ENTITIES:" not in user_prompt
    assert "RELATIONSHIPS:" not in user_prompt


def test_generate_truncates_lowest_scored_chunks_when_over_cap(monkeypatch) -> None:
    fake_complete, calls = _fake_complete_factory("Answer [AAPL_item1a_000].")
    monkeypatch.setattr(answer_module, "complete", fake_complete)
    monkeypatch.setattr(answer_module, "CONTEXT_CHAR_CAP", 100)

    result = RetrievalResult(
        chunks=[
            Chunk(id="AAPL_item1a_000", company="AAPL", section="item1a", text="x" * 60),
            Chunk(id="AAPL_item1a_001", company="AAPL", section="item1a", text="y" * 60),
            Chunk(id="AAPL_item1a_002", company="AAPL", section="item1a", text="z" * 60),
        ],
        entities=[],
        relations=[],
    )

    generate("question", result, mode="naive")

    user_prompt = calls[0]["user"]
    # The first (best-scored) chunk must survive; later ones get truncated to fit the cap.
    assert "AAPL_item1a_000" in user_prompt
    assert "AAPL_item1a_002" not in user_prompt
