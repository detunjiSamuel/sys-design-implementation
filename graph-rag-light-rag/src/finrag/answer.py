"""Prompt assembly + citation-grounded generation, shared by all three retrieval modes.

The context string always has the same shape — an optional ENTITIES table, an optional
RELATIONSHIPS table, and a SOURCE CHUNKS section — so the same prompt and the same
generator work for naive, graphrag, and lightrag. Naive retrieval never populates
entities/relations, so those sections are simply omitted; graphrag/lightrag fill them in.
This mirrors the LightRAG paper's context format and keeps `answer.py` retrieval-strategy
agnostic (it only knows about `RetrievalResult`, never about how it was produced).
"""

import re

from finrag.llm import complete
from finrag.models import Answer, RetrievalResult
from finrag.observability import span

# Rough token-to-char budget for the context we hand the model. Chunks are dropped
# lowest-scored-first (i.e. from the end of `result.chunks`, since every retriever returns
# chunks best-match-first) until the context fits. ~24k chars is comfortably inside every
# Claude model's context window even alongside entities/relations and the system prompt.
CONTEXT_CHAR_CAP = 24_000

SYSTEM_PROMPT = (
    "You are a financial analyst answering questions about SEC 10-K filings. "
    "Answer ONLY using the information in the provided context — never use outside "
    "knowledge or guess. After every claim you make, cite the chunk id(s) it came from "
    "in square brackets, e.g. [AAPL_item1a_003]. If the context does not contain enough "
    "information to answer the question, say so explicitly instead of guessing."
)

_CITATION_RE = re.compile(r"\[([A-Za-z0-9_]+)\]")


def _entities_section(result: RetrievalResult) -> str:
    if not result.entities:
        return ""
    rows = "\n".join(f"- {e.name} ({e.type}): {e.description}" for e in result.entities)
    return f"ENTITIES:\n{rows}\n"


def _relations_section(result: RetrievalResult) -> str:
    if not result.relations:
        return ""
    rows = "\n".join(
        f"- {r.source} -> {r.target} (strength {r.strength}, keywords: {', '.join(r.keywords)}): "
        f"{r.description}"
        for r in result.relations
    )
    return f"RELATIONSHIPS:\n{rows}\n"


def _build_context(result: RetrievalResult, char_cap: int) -> tuple[str, bool, int]:
    """Assemble the labeled context string, truncating lowest-scored chunks first if it
    would exceed `char_cap`. Returns (context, was_truncated, chunks_dropped).
    """
    header_parts = [p for p in (_entities_section(result), _relations_section(result)) if p]
    header = "\n".join(header_parts)
    budget = char_cap - len(header)

    kept_chunk_blocks: list[str] = []
    used = 0
    dropped = 0
    for chunk in result.chunks:  # best-match-first; we truncate from the tail
        block = f"[{chunk.id}] {chunk.text}"
        if used + len(block) > max(budget, 0):
            dropped += 1
            continue
        kept_chunk_blocks.append(block)
        used += len(block)

    chunks_section = "SOURCE CHUNKS:\n" + "\n\n".join(kept_chunk_blocks) if kept_chunk_blocks else "SOURCE CHUNKS:\n(none)"

    sections = [p for p in (header, chunks_section) if p]
    return "\n\n".join(sections), dropped > 0, dropped


def generate(question: str, result: RetrievalResult, mode: str) -> Answer:
    """Build the context, call the LLM, and parse cited chunk ids out of the response."""
    with span("generate", mode=mode) as record:
        context, truncated, dropped = _build_context(result, CONTEXT_CHAR_CAP)
        record["attrs"]["truncated"] = truncated
        record["attrs"]["chunks_dropped"] = dropped
        # Stashed (not returned — Answer's shape is fixed) so `finrag ask --show-context`
        # can print exactly what the model saw via observability.last_span("generate").
        record["attrs"]["context"] = context

        user_prompt = f"{context}\n\nQUESTION: {question}"
        text = complete(system=SYSTEM_PROMPT, user=user_prompt)

        known_ids = {chunk.id for chunk in result.chunks}
        cited = []
        for match in _CITATION_RE.findall(text):
            if match in known_ids and match not in cited:
                cited.append(match)

        return Answer(text=text, citations=cited, mode=mode)
