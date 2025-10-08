
FROM python:3.12-slim AS base

WORKDIR /app

# Install uv package manager
RUN pip install --no-cache-dir uv

# Copy dependency files first for caching
COPY pyproject.toml uv.lock ./

# Install dependencies (prod only)
RUN uv sync --frozen --no-dev

# Copy your application source
COPY server/app ./app

# Expose the app port
EXPOSE 8000

# Run FastAPI with Uvicorn
CMD ["uv", "run", "python" ,"-m" , "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

