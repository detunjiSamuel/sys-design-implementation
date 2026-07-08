"""evals/run_evals.py tests: monkeypatch `pipeline.ask` (canned Answers) and the judge's
`llm.extract` (fixed Judgments) -- no network, no real LLM, no real pipeline retrieval.

Runs run_evals() on a small 2-question temp YAML across 2 modes and checks: results.md is
written with the three expected sections, the returned aggregate's means are computed
correctly, and a mode that raises for one question still produces a complete report with a
zero-score row for that cell instead of aborting the run.
"""

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root, for `evals.*`

from evals import run_evals as run_evals_module
from evals.run_evals import Judgment, run_evals
from finrag.models import Answer


@pytest.fixture()
def questions_path(tmp_path) -> Path:
    questions = [
        {
            "id": "local_01",
            "tier": "local",
            "question": "What does Apple say about supply chain risk?",
            "gold": "Apple relies on a concentrated set of outsourced manufacturers.",
        },
        {
            "id": "global_01",
            "tier": "global",
            "question": "What macro risks recur across all six companies?",
            "gold": "Inflation, interest rates, and recession risk recur across all six.",
        },
    ]
    path = tmp_path / "questions.yaml"
    path.write_text(yaml.safe_dump(questions), encoding="utf-8")
    return path


def _patch_ask_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_ask(question: str, mode: str = "auto") -> Answer:
        return Answer(text=f"[{mode}] answer to: {question}", citations=[], mode=mode)

    monkeypatch.setattr(run_evals_module.pipeline, "ask", fake_ask)


def _patch_judge_fixed(monkeypatch: pytest.MonkeyPatch, correctness: int, completeness: int) -> None:
    def fake_llm_extract(**kwargs):
        return Judgment(correctness=correctness, completeness=completeness, rationale="matches gold")

    monkeypatch.setattr(run_evals_module, "llm_extract", fake_llm_extract)


def test_run_evals_writes_report_with_expected_sections(
    monkeypatch: pytest.MonkeyPatch, questions_path: Path, tmp_path: Path
) -> None:
    _patch_ask_ok(monkeypatch)
    _patch_judge_fixed(monkeypatch, correctness=4, completeness=3)

    out_path = tmp_path / "results.md"
    aggregate = run_evals(modes=("naive", "graphrag"), questions_path=questions_path, out_path=out_path)

    assert out_path.exists()
    text = out_path.read_text(encoding="utf-8")
    assert "## Headline: correctness / completeness by tier and mode" in text
    assert "## Cost and latency by mode" in text
    assert "## Per-question detail" in text
    # headline table has both modes as columns and both tiers as rows
    assert "| naive | graphrag |" in text
    assert "| local |" in text
    assert "| global |" in text
    # per-question detail lists every (question, mode) cell
    assert "local_01" in text and "global_01" in text

    assert aggregate["tiers"] == ["local", "global"]
    assert aggregate["modes"] == ["naive", "graphrag"]
    assert len(aggregate["rows"]) == 4  # 2 questions x 2 modes


def test_run_evals_aggregate_means_are_correct(
    monkeypatch: pytest.MonkeyPatch, questions_path: Path, tmp_path: Path
) -> None:
    _patch_ask_ok(monkeypatch)
    _patch_judge_fixed(monkeypatch, correctness=4, completeness=2)

    aggregate = run_evals(
        modes=("naive",), questions_path=questions_path, out_path=tmp_path / "results.md"
    )

    # every cell scored (4, 2), so every tier's mean for "naive" must be exactly (4.0, 2.0).
    for tier in ("local", "global"):
        stats = aggregate["by_tier_mode"][tier]["naive"]
        assert stats["correctness"] == pytest.approx(4.0)
        assert stats["completeness"] == pytest.approx(2.0)
        assert stats["n"] == 1

    mode_stats = aggregate["by_mode"]["naive"]
    assert mode_stats["n"] == 2
    # no real span was opened around fake_ask, so latency/cost default to 0.0 -- still a
    # well-defined mean, not a crash.
    assert mode_stats["cost_usd"] == pytest.approx(0.0)


def test_run_evals_survives_a_raising_mode_with_zero_score_row(
    monkeypatch: pytest.MonkeyPatch, questions_path: Path, tmp_path: Path
) -> None:
    def flaky_ask(question: str, mode: str = "auto") -> Answer:
        if mode == "lightrag":
            raise RuntimeError("boom: retriever exploded")
        return Answer(text=f"[{mode}] fine", citations=[], mode=mode)

    monkeypatch.setattr(run_evals_module.pipeline, "ask", flaky_ask)
    _patch_judge_fixed(monkeypatch, correctness=5, completeness=5)

    out_path = tmp_path / "results.md"
    aggregate = run_evals(
        modes=("naive", "lightrag"), questions_path=questions_path, out_path=out_path
    )

    # the run completes and writes a full report despite one mode always raising.
    assert out_path.exists()
    assert len(aggregate["rows"]) == 4

    lightrag_rows = [r for r in aggregate["rows"] if r["mode"] == "lightrag"]
    assert len(lightrag_rows) == 2
    for row in lightrag_rows:
        assert row["correctness"] == 0
        assert row["completeness"] == 0
        assert row["error"] is not None
        assert "boom: retriever exploded" in row["rationale"]

    naive_rows = [r for r in aggregate["rows"] if r["mode"] == "naive"]
    for row in naive_rows:
        assert row["correctness"] == 5
        assert row["error"] is None

    # the failing mode's tier means are dragged to 0, not silently dropped from the table.
    assert aggregate["by_tier_mode"]["local"]["lightrag"]["correctness"] == 0
    assert aggregate["by_tier_mode"]["local"]["naive"]["correctness"] == 5

    text = out_path.read_text(encoding="utf-8")
    assert "ERROR: boom: retriever exploded" in text


def test_judge_calls_llm_extract_with_judgment_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_llm_extract(*, system, user, schema, model=None):
        captured["system"] = system
        captured["user"] = user
        captured["schema"] = schema
        return Judgment(correctness=5, completeness=5, rationale="perfect match")

    monkeypatch.setattr(run_evals_module, "llm_extract", fake_llm_extract)

    result = run_evals_module.judge("Q?", "gold answer", "candidate answer")

    assert isinstance(result, Judgment)
    assert captured["schema"] is Judgment
    assert "gold answer" in captured["user"]
    assert "candidate answer" in captured["user"]
