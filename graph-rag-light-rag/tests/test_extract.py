"""extract.py tests: monkeypatch `llm.extract` with a fake, no network involved.

`_dummy_env` (tests/conftest.py, autouse) already points settings.data_dir at a per-test
tmp_path, so extract_all's checkpoint file (data/extractions.jsonl) never touches the
real project directory.
"""

import pytest

from finrag import extract as extract_module
from finrag.models import Chunk, Entity, Extraction, Relation


def _fake_extraction() -> Extraction:
    return Extraction(
        entities=[
            Entity(name="apple inc", type="COMPANY", description="Maker of iPhones."),
            Entity(name="tsmc", type="COMPANY", description="Chip fabricator."),
        ],
        relations=[
            Relation(
                source="apple inc",
                target="tsmc",
                description="Apple depends on TSMC for chip fabrication.",
                keywords=["supply chain"],
                strength=8,
            ),
            Relation(
                source="apple inc",
                target="unknown corp",  # never in the entities list -> must be dropped
                description="Bogus relation to an entity that wasn't extracted.",
                keywords=["x"],
                strength=1,
            ),
        ],
    )


def _chunk(chunk_id: str) -> Chunk:
    return Chunk(id=chunk_id, company="AAPL", section="item1a", text=f"text for {chunk_id}")


def test_extract_chunk_normalizes_names_and_drops_unknown_relations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(extract_module, "llm_extract", lambda **kwargs: _fake_extraction())

    result = extract_module.extract_chunk(_chunk("AAPL_item1a_000"))

    # lowercase names from the LLM are normalized to .strip().upper() in code.
    assert {e.name for e in result.entities} == {"APPLE INC", "TSMC"}
    # the relation pointing at "unknown corp" (never extracted as an entity) is dropped.
    assert len(result.relations) == 1
    assert result.relations[0].source == "APPLE INC"
    assert result.relations[0].target == "TSMC"


def test_extract_all_is_checkpointed_and_resumable(monkeypatch: pytest.MonkeyPatch) -> None:
    call_count = 0

    def fake_llm_extract(**kwargs):
        nonlocal call_count
        call_count += 1
        return _fake_extraction()

    monkeypatch.setattr(extract_module, "llm_extract", fake_llm_extract)

    chunks = [_chunk("c1"), _chunk("c2"), _chunk("c3")]

    extract_module.extract_all(chunks[:2])
    assert call_count == 2

    # Re-run with a 3rd chunk added: c1/c2 are already in the checkpoint file, so only
    # c3 should trigger a new LLM call.
    extract_module.extract_all(chunks)
    assert call_count == 3

    extractions = extract_module.load_extractions()
    assert {chunk_id for chunk_id, _ in extractions} == {"c1", "c2", "c3"}


def test_extract_all_skips_failed_chunk_and_continues(monkeypatch: pytest.MonkeyPatch) -> None:
    def flaky_llm_extract(system, user, schema, model=None):
        if "bad" in user:
            raise RuntimeError("boom")
        return _fake_extraction()

    monkeypatch.setattr(extract_module, "llm_extract", flaky_llm_extract)

    extract_module.extract_all([_chunk("good1"), _chunk("bad"), _chunk("good2")])

    extractions = dict(extract_module.load_extractions())
    assert set(extractions.keys()) == {"good1", "good2"}
