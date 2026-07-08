"""Every configuration knob for the project lives here, and nowhere else.

Loaded once from `.env` (or real environment variables) into the module-level `settings`
singleton. Most fields are namespaced with the `FINRAG_` prefix so they don't collide with
other tools' env vars, but a few are read as-is because they're conventionally named by the
services that define them: ANTHROPIC_API_KEY (the Anthropic SDK convention), NEO4J_* (the
docker image's own env vars), and EDGAR_IDENTITY (edgartools' required User-Agent string).
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# USD cost per million tokens, as (input, output). Used by observability.py to price
# every LLM call. Add a model here before pointing any *_model setting at it.
PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-8": (5.00, 25.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="FINRAG_",
        extra="ignore",
    )

    # --- Anthropic ---
    # No FINRAG_ prefix: this is the name the `anthropic` SDK itself looks for.
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    answer_model: str = "claude-opus-4-8"
    extract_model: str = "claude-opus-4-8"
    judge_model: str = "claude-opus-4-8"

    # --- Langfuse --- (no prefix: matches the langfuse SDK's own env var convention)
    # Optional. Unset (the default) keeps observability.py's Langfuse mirror completely
    # inert -- local JSONL tracing (runs/traces/) works either way. Sign up free at
    # https://cloud.langfuse.com to get a public/secret key pair.
    langfuse_public_key: str = Field(default="", validation_alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", validation_alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(
        default="https://cloud.langfuse.com", validation_alias="LANGFUSE_HOST"
    )

    # --- Neo4j --- (no prefix: matches the docker-compose / neo4j driver convention)
    neo4j_uri: str = Field(default="bolt://localhost:7687", validation_alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", validation_alias="NEO4J_USER")
    neo4j_password: str = Field(default="password", validation_alias="NEO4J_PASSWORD")

    # --- EDGAR --- (no prefix: this is edgartools' own concept, "name email@example.com")
    edgar_identity: str = Field(
        default="FinGraphRAG dev dev@example.com", validation_alias="EDGAR_IDENTITY"
    )

    # --- Corpus ---
    tickers: list[str] = ["AAPL", "MSFT", "NVDA", "JPM", "XOM", "PFE"]

    # --- Chunking ---
    chunk_size: int = 4000
    chunk_overlap: int = 400

    # --- Retrieval ---
    top_k_chunks: int = 8
    top_k_entities: int = 5
    hops: int = 2

    # --- Paths ---
    data_dir: Path = Path("data")
    runs_dir: Path = Path("runs")

    # Cost table lives in config (not observability.py) so switching a model in one place
    # automatically updates cost accounting everywhere. See PRICING above.
    pricing: dict[str, tuple[float, float]] = PRICING


settings = Settings()
