"""The shared retriever interface.

Naive, GraphRAG, and LightRAG retrieval look nothing alike internally — one is a single
vector lookup, the other two walk a graph — but `pipeline.py` and `answer.py` need to treat
them interchangeably: pick a mode, call `retrieve(question)`, hand the result to the
generator. A `Protocol` with one method is exactly enough surface area to make that
swap possible without an inheritance hierarchy (PLAN.md's "no inheritance trees" rule) —
each retriever is just a class with a `name` attribute and a `retrieve` method, structurally
typed.
"""

from typing import Protocol

from finrag.models import RetrievalResult


class Retriever(Protocol):
    name: str

    def retrieve(self, question: str) -> RetrievalResult: ...
