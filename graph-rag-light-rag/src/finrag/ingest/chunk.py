"""data/raw/*.txt -> data/chunks.jsonl

Splits each raw section file into overlapping chunks and writes one Chunk (as JSON) per
line. `load_chunks()` is the read-side counterpart used by every later phase (indexing,
extraction, retrieval) so nothing downstream needs to know about the file format.
"""

import json

from langchain_text_splitters import RecursiveCharacterTextSplitter

from finrag.config import settings
from finrag.models import Chunk


def _parse_filename(path_stem: str) -> tuple[str, str]:
    """"{ticker}_{section}" -> (ticker, section). Filenames are written by download.py."""
    ticker, section = path_stem.split("_", 1)
    return ticker, section


def chunk_all() -> list[Chunk]:
    """Read every data/raw/*.txt file, split it, and write data/chunks.jsonl.

    Chunk ids are stable ("{ticker}_{section}_{n:03d}") so rerunning on unchanged input
    produces byte-identical output.
    """
    raw_dir = settings.data_dir / "raw"
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )

    chunks: list[Chunk] = []
    for path in sorted(raw_dir.glob("*.txt")):
        ticker, section = _parse_filename(path.stem)
        text = path.read_text(encoding="utf-8")
        for i, piece in enumerate(splitter.split_text(text)):
            chunks.append(
                Chunk(
                    id=f"{ticker}_{section}_{i:03d}",
                    company=ticker,
                    section=section,
                    text=piece,
                )
            )

    out_path = settings.data_dir / "chunks.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(chunk.model_dump_json() + "\n")

    print(f"wrote {len(chunks)} chunks to {out_path}")
    return chunks


def load_chunks() -> list[Chunk]:
    """Read data/chunks.jsonl back into Chunk models. Used by indexing/extraction/retrieval."""
    path = settings.data_dir / "chunks.jsonl"
    chunks = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(Chunk.model_validate_json(line))
    return chunks
