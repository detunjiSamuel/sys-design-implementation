FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends openjdk-21-jre-headless && \
    rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Pre-download the VADER lexicon so it is baked into the image
RUN /app/.venv/bin/python -c "import nltk; nltk.download('vader_lexicon')"

COPY logging_config.py ./
COPY sparkAnalysis/ sparkAnalysis/

ENV PATH="/app/.venv/bin:$PATH"

CMD ["python", "-m", "sparkAnalysis.main"]
