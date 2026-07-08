"""The eval harness (PLAN.md Phase 6) — the table that justifies the whole project.

For every question in `questions.yaml` and every retrieval mode, this:
  1. runs the question through `pipeline.ask(question, mode=mode)`,
  2. asks an LLM judge to score the resulting answer against the question's `gold`
     reference (the judge sees the question + gold + candidate answer, never the
     retrieved context — see the module docstring on `JUDGE_PROMPT` for why),
  3. pulls latency/token/cost numbers out of the same observability trace summary the
     CLI already prints (`observability.last_span("ask")`, exactly like cli.py's `ask`
     command does — see its comment on why `last_span` rather than widening `Answer`),
  4. writes `evals/results.md` with a headline tier x mode table, a cost/latency table,
     and a per-question detail table, and returns the same numbers as a dict.

Failure handling mirrors PLAN.md section 6's policy for extraction: a single question x
mode cell failing (pipeline error, judge error, whatever) is logged as a zero-score row
with the error string attached. It never aborts the run — a 24 x 3 grid should survive one
bad cell the same way a 400-chunk extraction survives one bad chunk.

Runnable directly (`python evals/run_evals.py --modes naive,graphrag --questions ...`) and
importable (`from evals.run_evals import run_evals`) — `finrag eval` in cli.py imports and
calls `run_evals` the same way this module's own `main()` does.
"""

import argparse
import statistics
from pathlib import Path
from typing import Iterable

import yaml
from pydantic import BaseModel, Field
from rich.console import Console
from rich.progress import Progress

from finrag import pipeline
from finrag.config import settings
from finrag.llm import extract as llm_extract
from finrag.observability import last_span

# Paths are anchored to this file's directory (not the process cwd) so `run_evals()`
# behaves the same whether it's invoked as `python evals/run_evals.py` from the repo
# root, via pytest from anywhere, or via `finrag eval` from an arbitrary cwd.
_EVALS_DIR = Path(__file__).resolve().parent
DEFAULT_QUESTIONS_PATH = _EVALS_DIR / "questions.yaml"
DEFAULT_RESULTS_PATH = _EVALS_DIR / "results.md"

# Canonical display order; only tiers actually present in the question set are rendered
# (so a small test fixture with one tier doesn't print two empty rows).
TIER_ORDER = ["local", "multi_hop", "global"]
DEFAULT_MODES = ("naive", "graphrag", "lightrag")

JUDGE_SYSTEM_PROMPT = """\
You are grading a candidate answer to a question about SEC 10-K filings against a gold
reference answer written by a human analyst. You are NOT shown the retrieved context the
candidate had available — score only how well the candidate's final text matches the gold
answer's content. Do not reward or penalize citation formatting.

Score two dimensions, each on a 1-5 integer scale:

correctness -- are the candidate's factual claims consistent with the gold answer?
  1 = the candidate contradicts the gold answer, or states specific facts (numbers,
      names, causal claims) that the gold answer does not support.
  3 = the candidate is broadly consistent with the gold answer but has a partial error,
      an unsupported specific claim, or is vague/hedged where the gold answer is specific.
  5 = every factual claim the candidate makes is consistent with the gold answer (the
      candidate may use different wording).

completeness -- how much of the gold answer's content does the candidate cover?
  1 = the candidate covers almost none of the gold answer's key points, refuses to
      answer, or answers a different question than the one asked.
  3 = the candidate covers roughly half of the gold answer's key points.
  5 = the candidate covers all (or nearly all) of the gold answer's key points; it may
      also include additional correct information.

Give a one-sentence rationale that justifies both scores together.
"""


class Judgment(BaseModel):
    """Structured-output schema for the LLM judge. See JUDGE_SYSTEM_PROMPT for exactly
    what 1 / 3 / 5 mean on each scale.
    """

    correctness: int = Field(ge=1, le=5)
    completeness: int = Field(ge=1, le=5)
    rationale: str


def judge(question: str, gold: str, candidate: str) -> Judgment:
    """Score one candidate answer against its gold reference. The judge never sees the
    retrieval context — PLAN.md section 7's question "why does the judge see the gold
    answer but not the retrieved context" — the point is to score the *answer users would
    read*, not to re-grade retrieval; retrieval-level scoring is a stretch goal
    (PLAN.md stretch goal 5, chunk-recall against hand-labeled relevant chunks).
    """
    user = f"QUESTION:\n{question}\n\nGOLD ANSWER:\n{gold}\n\nCANDIDATE ANSWER:\n{candidate}"
    return llm_extract(
        system=JUDGE_SYSTEM_PROMPT, user=user, schema=Judgment, model=settings.judge_model
    )


def load_questions(path: str | Path) -> list[dict]:
    """Read questions.yaml (a list of {id, tier, question, gold} dicts) off disk."""
    with Path(path).open(encoding="utf-8") as f:
        questions = yaml.safe_load(f)
    return questions or []


def _mean(values: list[float]) -> float:
    return statistics.mean(values) if values else 0.0


def _run_one_cell(question: dict, mode: str) -> dict:
    """Run a single (question, mode) pair end to end. Never raises: any failure in
    `pipeline.ask` or `judge` is caught and turned into a zero-score row carrying the
    error string, so one bad cell can't abort the other 23 x N cells.
    """
    row = {"id": question["id"], "tier": question["tier"], "mode": mode}
    try:
        answer = pipeline.ask(question["question"], mode=mode)
        root = last_span("ask")
        summary = root.get("summary", {}) if root else {}
        verdict = judge(question["question"], question["gold"], answer.text)
        row.update(
            correctness=verdict.correctness,
            completeness=verdict.completeness,
            rationale=verdict.rationale,
            latency_ms=summary.get("latency_ms", 0.0),
            cost_usd=summary.get("cost_usd", 0.0),
            error=None,
        )
    except Exception as exc:  # noqa: BLE001 - one bad cell must not kill the eval run
        row.update(
            correctness=0,
            completeness=0,
            rationale=f"ERROR: {exc}",
            latency_ms=0.0,
            cost_usd=0.0,
            error=str(exc),
        )
    return row


def _aggregate(rows: list[dict], modes: Iterable[str]) -> dict:
    """Reduce the flat per-cell rows into the two views results.md renders: tier x mode
    (correctness/completeness) and mode-only (cost/latency).
    """
    tiers_present = [t for t in TIER_ORDER if any(r["tier"] == t for r in rows)]
    modes = list(modes)

    by_tier_mode: dict[str, dict[str, dict]] = {}
    for tier in tiers_present:
        by_tier_mode[tier] = {}
        for mode in modes:
            cell_rows = [r for r in rows if r["tier"] == tier and r["mode"] == mode]
            by_tier_mode[tier][mode] = {
                "correctness": _mean([r["correctness"] for r in cell_rows]),
                "completeness": _mean([r["completeness"] for r in cell_rows]),
                "n": len(cell_rows),
            }

    by_mode: dict[str, dict] = {}
    for mode in modes:
        mode_rows = [r for r in rows if r["mode"] == mode]
        by_mode[mode] = {
            "cost_usd": _mean([r["cost_usd"] for r in mode_rows]),
            "latency_ms": _mean([r["latency_ms"] for r in mode_rows]),
            "total_cost_usd": sum(r["cost_usd"] for r in mode_rows),
            "n": len(mode_rows),
        }

    return {"tiers": tiers_present, "modes": modes, "by_tier_mode": by_tier_mode, "by_mode": by_mode, "rows": rows}


def _write_report(aggregate: dict, out_path: Path) -> None:
    tiers = aggregate["tiers"]
    modes = aggregate["modes"]
    by_tier_mode = aggregate["by_tier_mode"]
    by_mode = aggregate["by_mode"]
    rows = aggregate["rows"]

    lines: list[str] = []
    lines.append("# FinGraphRAG eval results")
    lines.append("")
    lines.append(
        "Generated by `evals/run_evals.py`. Correctness and completeness are LLM-judge "
        "scores on a 1-5 scale (see `JUDGE_PROMPT` in run_evals.py for the rubric); the "
        "judge sees the question, the gold answer, and the candidate answer, never the "
        "retrieved context."
    )
    lines.append("")

    # (a) headline table: tier x mode, cell = "correctness / completeness"
    lines.append("## Headline: correctness / completeness by tier and mode")
    lines.append("")
    header = "| tier | " + " | ".join(modes) + " |"
    sep = "|---|" + "---|" * len(modes)
    lines.append(header)
    lines.append(sep)
    for tier in tiers:
        cells = []
        for mode in modes:
            stats = by_tier_mode[tier][mode]
            cells.append(f"{stats['correctness']:.1f} / {stats['completeness']:.1f}")
        lines.append(f"| {tier} | " + " | ".join(cells) + " |")
    lines.append("")
    n_per_tier = {tier: by_tier_mode[tier][modes[0]]["n"] if modes else 0 for tier in tiers}
    lines.append(
        "Each cell is mean(correctness) / mean(completeness) across the tier's questions "
        f"({', '.join(f'{t}: n={n}' for t, n in n_per_tier.items())})."
    )
    lines.append("")

    # (b) cost & latency per mode
    lines.append("## Cost and latency by mode")
    lines.append("")
    lines.append("| mode | mean cost/query | mean latency/query | total cost | n |")
    lines.append("|---|---|---|---|---|")
    for mode in modes:
        stats = by_mode[mode]
        lines.append(
            f"| {mode} | ${stats['cost_usd']:.4f} | {stats['latency_ms'] / 1000:.1f}s | "
            f"${stats['total_cost_usd']:.4f} | {stats['n']} |"
        )
    lines.append("")

    # (c) per-question detail
    lines.append("## Per-question detail")
    lines.append("")
    lines.append("| id | tier | mode | correctness | completeness | rationale |")
    lines.append("|---|---|---|---|---|---|")
    for row in rows:
        rationale = row["rationale"].replace("\n", " ").replace("|", "/")
        lines.append(
            f"| {row['id']} | {row['tier']} | {row['mode']} | {row['correctness']} | "
            f"{row['completeness']} | {rationale} |"
        )
    lines.append("")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def run_evals(
    modes: tuple[str, ...] = DEFAULT_MODES,
    questions_path: str | Path = DEFAULT_QUESTIONS_PATH,
    out_path: str | Path = DEFAULT_RESULTS_PATH,
) -> dict:
    """Run every question x mode, judge every answer, write `evals/results.md`, and
    return the same numbers as a dict (`{"tiers", "modes", "by_tier_mode", "by_mode",
    "rows"}`) so callers (tests, notebooks, `finrag eval`) don't have to re-parse markdown.
    """
    questions = load_questions(questions_path)
    console = Console()
    console.print(
        f"eval: {len(questions)} questions x {len(modes)} modes = "
        f"{len(questions) * len(modes)} runs"
    )

    rows: list[dict] = []
    with Progress() as progress:
        task = progress.add_task("evaluating", total=len(questions) * len(modes))
        for question in questions:
            for mode in modes:
                rows.append(_run_one_cell(question, mode))
                progress.advance(task)

    aggregate = _aggregate(rows, modes)
    _write_report(aggregate, Path(out_path))

    n_errors = sum(1 for r in rows if r["error"] is not None)
    console.print(f"eval done: wrote {out_path} ({n_errors} cell(s) errored)")

    return aggregate


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the FinGraphRAG eval harness: every question x every retrieval "
        "mode, LLM-judged against gold answers, written to evals/results.md."
    )
    parser.add_argument(
        "--modes",
        default=",".join(DEFAULT_MODES),
        help="Comma-separated retrieval modes to evaluate (default: naive,graphrag,lightrag).",
    )
    parser.add_argument(
        "--questions",
        default=str(DEFAULT_QUESTIONS_PATH),
        help="Path to the questions YAML file (default: evals/questions.yaml).",
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_RESULTS_PATH),
        help="Path to write the results report to (default: evals/results.md).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    modes = tuple(m.strip() for m in args.modes.split(",") if m.strip())
    run_evals(modes=modes, questions_path=args.questions, out_path=args.out)


if __name__ == "__main__":
    main()
