"""Shared pytest fixtures. Sets dummy env vars so `Settings()` constructs without a real
.env file, an API key, or a running Neo4j — the whole suite runs offline. Also redirects
`settings.data_dir`/`settings.runs_dir` to a per-test tmp_path so tests never write into
the real project's data/ or runs/ directories, even if a test forgets to do it itself.
"""

import pytest

from finrag.config import settings


@pytest.fixture(autouse=True)
def _dummy_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-dummy")
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "password")
    monkeypatch.setenv("EDGAR_IDENTITY", "Test Suite test@example.com")
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "runs_dir", tmp_path / "runs")
