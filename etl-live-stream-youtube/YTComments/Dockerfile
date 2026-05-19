FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY logging_config.py ./
COPY YTComments/ YTComments/

ENV PATH="/app/.venv/bin:$PATH"

CMD ["python", "-m", "YTComments.main"]
