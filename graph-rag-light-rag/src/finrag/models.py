"""Pydantic data shapes shared by every module in this project.

These are the "nouns" of the system: a Chunk is a slice of a filing, an Entity/Relation
pair is what the LLM extracts from chunks to build the knowledge graph, and
RetrievalResult/Answer are what a retriever and the answer generator hand back. Keeping
them all in one file means every module can import from `finrag.models` without
depending on each other.
"""

from pydantic import BaseModel


class Chunk(BaseModel):
    """A contiguous slice of a 10-K section, small enough to embed and cite.

    `id` is stable and human-readable: "{ticker}_{section}_{n:03d}", e.g. "AAPL_item1a_007".
    That makes citations in generated answers ("[AAPL_item1a_007]") traceable back to
    data/chunks.jsonl without a lookup table.
    """

    id: str
    company: str
    section: str
    text: str


class Entity(BaseModel):
    """A node in the knowledge graph: a company, person, product, risk, etc.

    `type` is a free-text label (COMPANY, PERSON, PRODUCT, RISK, REGULATION, METRIC, ...)
    chosen by the extraction prompt, not a Python enum — new entity types shouldn't require
    a code change, just a prompt tweak.
    """

    name: str
    type: str
    description: str


class Relation(BaseModel):
    """A directed, described edge between two entities.

    `description` is the natural-language sentence explaining the relationship — this is
    the piece LightRAG embeds and searches over for "high-level" (thematic) retrieval,
    instead of building an expensive community-summarization index.
    """

    source: str
    target: str
    description: str
    keywords: list[str]
    strength: int  # 1-10, LLM-assigned; used to rank/cap edges when a neighborhood is large


class Extraction(BaseModel):
    """The structured-output schema handed to `llm.extract()` during graph construction.

    One Extraction is produced per chunk: everything the LLM found in that chunk.
    """

    entities: list[Entity]
    relations: list[Relation]


class QueryKeywords(BaseModel):
    """The structured-output schema for LightRAG's dual-level query decomposition.

    `low_level` are concrete entity mentions (e.g. "Apple", "TSMC") matched against the
    Chroma `entities` collection for local, specific retrieval. `high_level` are thematic
    terms (e.g. "supply chain concentration") matched against the `relations` collection
    for global, cross-entity retrieval.
    """

    low_level: list[str]
    high_level: list[str]


class RetrievalResult(BaseModel):
    """What every retriever (naive/graphrag/lightrag) returns — a common shape so the
    answer generator doesn't need to know which retrieval strategy produced it.
    """

    chunks: list[Chunk]
    entities: list[Entity]
    relations: list[Relation]


class Answer(BaseModel):
    """The final output of a query: generated text, the chunk ids it cited, and which
    retrieval mode produced it (useful for eval reports and for the CLI trace summary).
    """

    text: str
    citations: list[str]
    mode: str
