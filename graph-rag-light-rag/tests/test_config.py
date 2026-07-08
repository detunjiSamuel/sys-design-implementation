"""Defaults tests for config.Settings — every knob should have the value PLAN.md specifies."""

from pathlib import Path

from finrag.config import PRICING, Settings


def test_model_defaults() -> None:
    s = Settings()
    assert s.answer_model == "claude-opus-4-8"
    assert s.extract_model == "claude-opus-4-8"
    assert s.judge_model == "claude-opus-4-8"


def test_neo4j_defaults_read_without_prefix() -> None:
    s = Settings()
    assert s.neo4j_uri == "bolt://localhost:7687"
    assert s.neo4j_user == "neo4j"
    assert s.neo4j_password == "password"


def test_anthropic_key_read_from_env(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-abc123")
    s = Settings()
    assert s.anthropic_api_key == "sk-ant-abc123"


def test_tickers_default() -> None:
    s = Settings()
    assert s.tickers == ["AAPL", "MSFT", "NVDA", "JPM", "XOM", "PFE"]


def test_chunking_defaults() -> None:
    s = Settings()
    assert s.chunk_size == 4000
    assert s.chunk_overlap == 400


def test_retrieval_defaults() -> None:
    s = Settings()
    assert s.top_k_chunks == 8
    assert s.top_k_entities == 5
    assert s.hops == 2


def test_paths_are_paths() -> None:
    s = Settings()
    assert isinstance(s.data_dir, Path)
    assert isinstance(s.runs_dir, Path)


def test_pricing_table() -> None:
    assert PRICING["claude-opus-4-8"] == (5.00, 25.00)
    assert PRICING["claude-haiku-4-5"] == (1.00, 5.00)
    s = Settings()
    assert s.pricing == PRICING
