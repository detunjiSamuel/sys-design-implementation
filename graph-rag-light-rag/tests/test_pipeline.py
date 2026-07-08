"""pipeline.py tests: fake llm.extract (classify) and fake retrievers/generate, no
network. Checks the conditional entry point (explicit mode skips classify entirely, auto
mode routes through it) and that ask() returns an Answer carrying the mode that was
actually used.
"""

import pytest

from finrag import pipeline
from finrag.models import Answer, RetrievalResult


class _FakeRetriever:
    """A retriever stand-in that records the question it was asked and returns an empty
    RetrievalResult tagged with its own name so tests can see which mode actually ran.
    """

    def __init__(self, name: str, calls: list[str]) -> None:
        self.name = name
        self._calls = calls

    def retrieve(self, question: str) -> RetrievalResult:
        self._calls.append(self.name)
        return RetrievalResult(chunks=[], entities=[], relations=[])


def _patch_retriever(monkeypatch, mode: str, calls: list[str]) -> None:
    monkeypatch.setitem(pipeline.RETRIEVERS, mode, lambda: _FakeRetriever(mode, calls))


def _patch_generate(monkeypatch) -> list[dict]:
    calls: list[dict] = []

    def fake_generate(question: str, result: RetrievalResult, mode: str) -> Answer:
        calls.append({"question": question, "result": result, "mode": mode})
        return Answer(text=f"answer for {mode}", citations=[], mode=mode)

    monkeypatch.setattr(pipeline, "generate_answer", fake_generate)
    return calls


def test_explicit_mode_skips_classify(monkeypatch: pytest.MonkeyPatch) -> None:
    classify_calls = 0

    def fake_llm_extract(**kwargs):
        nonlocal classify_calls
        classify_calls += 1
        return pipeline._TierLabel(tier="global")  # would route to lightrag if it ran

    monkeypatch.setattr(pipeline, "llm_extract", fake_llm_extract)

    retrieve_calls: list[str] = []
    _patch_retriever(monkeypatch, "naive", retrieve_calls)
    generate_calls = _patch_generate(monkeypatch)

    answer = pipeline.ask("What was NVIDIA's data center revenue driver?", mode="naive")

    assert classify_calls == 0  # the classify LLM must never be called
    assert retrieve_calls == ["naive"]
    assert generate_calls[0]["mode"] == "naive"
    assert answer.mode == "naive"


@pytest.mark.parametrize(
    "tier,expected_mode",
    [("local", "naive"), ("multi_hop", "graphrag"), ("global", "lightrag")],
)
def test_auto_mode_routes_by_classify_output(
    monkeypatch: pytest.MonkeyPatch, tier: str, expected_mode: str
) -> None:
    monkeypatch.setattr(pipeline, "llm_extract", lambda **kwargs: pipeline._TierLabel(tier=tier))

    retrieve_calls: list[str] = []
    _patch_retriever(monkeypatch, expected_mode, retrieve_calls)
    generate_calls = _patch_generate(monkeypatch)

    answer = pipeline.ask("some question", mode="auto")

    assert retrieve_calls == [expected_mode]
    assert generate_calls[0]["mode"] == expected_mode
    assert answer.mode == expected_mode


def test_ask_returns_answer_from_generate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline, "llm_extract", lambda **kwargs: pipeline._TierLabel(tier="local"))
    _patch_retriever(monkeypatch, "naive", [])
    _patch_generate(monkeypatch)

    answer = pipeline.ask("a local question", mode="auto")

    assert isinstance(answer, Answer)
    assert answer.text == "answer for naive"
    assert answer.mode == "naive"
