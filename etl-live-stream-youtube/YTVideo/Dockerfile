FROM python:3.12-slim

# libgl1 + libglib2.0-0 are required by opencv-python-headless
RUN apt-get update && \
    apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY logging_config.py ./
COPY YTVideo/ YTVideo/

ENV PATH="/app/.venv/bin:$PATH"

CMD ["python", "-m", "YTVideo.main"]
