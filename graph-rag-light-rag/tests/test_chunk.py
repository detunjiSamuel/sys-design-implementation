"""chunk.py tests: split a synthetic raw file in tmp_path, check stable ids + jsonl roundtrip."""

from finrag.config import settings
from finrag.ingest.chunk import chunk_all, load_chunks


def test_chunk_all_produces_stable_ids_and_roundtrips(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "chunk_size", 200)
    monkeypatch.setattr(settings, "chunk_overlap", 20)

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    # Long enough text that the splitter has to produce multiple chunks at chunk_size=200.
    paragraph = "Apple faces significant risk from supply chain concentration in Asia. " * 20
    (raw_dir / "AAPL_item1a.txt").write_text(paragraph, encoding="utf-8")
    (raw_dir / "MSFT_item7.txt").write_text(paragraph, encoding="utf-8")

    chunks = chunk_all()

    assert len(chunks) > 2
    assert (tmp_path / "chunks.jsonl").exists()

    aapl_chunks = [c for c in chunks if c.company == "AAPL"]
    assert len(aapl_chunks) >= 2
    for i, c in enumerate(aapl_chunks):
        assert c.id == f"AAPL_item1a_{i:03d}"
        assert c.section == "item1a"

    reloaded = load_chunks()
    assert reloaded == chunks


def test_load_chunks_roundtrip_matches_written_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "JPM_item1.txt").write_text("JPMorgan is a large bank.", encoding="utf-8")

    chunk_all()
    chunks = load_chunks()

    assert len(chunks) == 1
    assert chunks[0].id == "JPM_item1_000"
    assert chunks[0].company == "JPM"
    assert chunks[0].text == "JPMorgan is a large bank."
