"""The only module that computes embeddings.

FastEmbed runs the model locally via ONNX (no torch, no API key), which keeps tests
hermetic and ingestion free. The model weights download once on first use and are cached
by fastembed itself under its own cache dir — not something we manage here.
"""

from fastembed import TextEmbedding

_model: TextEmbedding | None = None


def _get_model() -> TextEmbedding:
    """Lazy singleton: loading the model is slow, so do it once per process."""
    global _model
    if _model is None:
        _model = TextEmbedding("BAAI/bge-small-en-v1.5")
    return _model


def embed(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts. Order of the output matches order of the input."""
    model = _get_model()
    return [vector.tolist() for vector in model.embed(texts)]
