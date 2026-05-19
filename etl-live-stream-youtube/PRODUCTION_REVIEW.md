# Production Readiness Review — `etl-live-stream-youtube`

**Reviewed:** 2026-05-19  
**Reviewer:** Claude Code  
**Scope:** All Python modules, Go server, Docker infrastructure, and project tooling

---

## Summary

The codebase has a solid architectural idea: YouTube live chat → Kafka → Spark Structured Streaming → MongoDB → Go SSE server → frontend. The data flow is well thought-out. However, several issues across all layers — bugs, hardcoding, missing infrastructure, and absent tests — mean it cannot run reliably in production today. This document phases the remediation from most critical to least critical.

---

## Phase 1 — Critical Bug Fixes
> **Goal:** Make the code actually run correctly as written, before any cleanup.
> **Commit scope:** 1–2 commits, small and targeted.

### 1.1 — `SentimentProcessor.process_batch` accesses a field that does not exist

**File:** `sparkAnalysis/SentimentProcessor.py`, line 27  

```python
# Current (BROKEN) — the schema defines "comment", not a nested "snippet.displayMessage"
sentiment_scores = self.analyze_sentiment(comment.snippet.displayMessage)

# Correct — the Kafka payload and the Spark schema both use the field "comment"
sentiment_scores = self.analyze_sentiment(comment.comment)
```

The Kafka producer in `CommentCollector.py` sends `{ "comment": ..., "profile_image": ..., "author_name": ..., "published_at": ... }`. The Spark schema mirrors that. `snippet.displayMessage` is a YouTube API field that was never forwarded — every batch will throw an `AttributeError` and silently discard all data.

---

### 1.2 — Dictionary mutation during iteration in `_collection_loop`

**File:** `YTComments/CommentCollector.py`, line 22

```python
# Current (BROKEN) — deleting from self.active_videos while iterating it
for video_id, comment_instance in self.active_videos.items():
    ...
    del self.active_videos[video_id]  # raises RuntimeError at runtime
```

Fix: collect dead video IDs in a separate list, remove them after the loop.

---

### 1.3 — `asyncio.create_task` called inside `start()` without a running loop guarantee

**File:** `YTComments/CommentCollector.py`, line 13

`start()` is an `async` method that calls `asyncio.create_task(self._collection_loop())`. The task is fire-and-forget — there is no reference kept to it. Python may garbage-collect it before it runs. The task should be stored as an instance attribute (`self._loop_task = asyncio.create_task(...)`).

---

### 1.4 — `print` in `process_batch` silently swallows the actual exception

**File:** `sparkAnalysis/SentimentProcessor.py`, lines 48–54

```python
except Exception as e:
    print(
        "batch_processing_error",
        f"video_id={self.video_id}",
        f"batch_id={batch_id}"
    )
    # "e" is never logged — impossible to debug failures
```

The variable `e` is captured but never emitted. Every failure is invisible.

---

### 1.5 — Missing comma in `print` call produces wrong output

**File:** `sparkAnalysis/SentimentProcessor.py`, line 43

```python
print(
    "batch_processed",
    f"video_id={self.video_id}",
    f"batch_id={batch_id}"          # <-- no comma before next line
    f"comments_count={len(processed_comments)}"  # Python silently concatenates these two f-strings
)
```

Python string literal concatenation merges `f"batch_id={batch_id}"` and `f"comments_count=..."` into one string. The `batch_id` and count are glued together with no separator in the output.

---

## Phase 2 — Configuration & Environment Management
> **Goal:** Eliminate all hardcoding and make the project runnable by anyone with a `.env` file.
> **Commit scope:** 1 commit per service, or one combined "config cleanup" commit.

### 2.1 — Create a root `.env.example` for Python services

The Go server has `server/.example.env` but the Python services have no equivalent. Someone cloning the repo has no idea which env vars to provide. A root `.env.example` should document every variable across all services:

```
# YouTube
YT_API_KEY=

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# MongoDB
MONGODB_URI=
DATABASE=youtube_sentiment
COLLECTION=comments

# Go server
PORT=3000

# YTVideo
VIDEO_STREAM_PORT=5000
```

### 2.2 — Kafka address is hardcoded in two places

**Files:** `YTComments/CommentCollector.py` line 11, `sparkAnalysis/SentimentProcessor.py` line 47

Both use `localhost:9092` / `127.0.0.1:9092` as string literals. When running via Docker Compose, the broker is at `broker:9093`. This is why the Spark service would fail to connect even with everything else working. Both must read from `os.getenv("KAFKA_BOOTSTRAP_SERVERS")`.

### 2.3 — `API_KEY` is read at module import time, not at class instantiation

**File:** `YTComments/Comment.py`, line 4

```python
API_KEY = os.getenv("YT_API_KEY")  # module-level — evaluated before dotenv loads
```

If `load_dotenv()` hasn't been called yet when this module is first imported, `API_KEY` will be `None`. Move the lookup inside the `__init__` or the method that uses it, and raise a clear `ValueError` if it is missing.

### 2.4 — Video IDs are hardcoded in two separate `main.py` files

**Files:** `YTComments/main.py` line 5, `sparkAnalysis/main.py` line 17

```python
video_ids = ["JQDaaHJ9u1E"]  # hardcoded in both places independently
```

These should come from an env var (`VIDEO_IDS=id1,id2`) or a config file. Having the same hardcoded value in two places guarantees they will drift.

### 2.5 — `load_dotenv()` is called in every module independently

`sparkAnalysis/main.py`, `sparkAnalysis/SentimentCollector.py`, and `YTVideo/main.py` each call `load_dotenv()`. There should be one call at the application entry point (`main.py`). Repeated calls are harmless but indicate there is no single bootstrap path.

### 2.6 — `DATABASE` and `COLLECTION` env var names conflict with the Go server's names

The Go server reads `DB_NAME` and `COLLECTION_NAME`. The Python services read `DATABASE` and `COLLECTION`. They talk to the same MongoDB instance. The naming should be consistent across the stack.

### 2.7 — `youtube-dl` is end-of-life

**File:** `YTVideo/main.py`, line 16

`youtube-dl` has not been maintained since 2021. Its successor `yt-dlp` is a drop-in replacement. `youtube-dl` will fail on most streams today.

---

## Phase 3 — Logging & Observability
> **Goal:** Replace all `print()` calls with structured logging so that log aggregators (Datadog, CloudWatch, Loki, etc.) can parse and alert on events.
> **Commit scope:** One commit per service or one "logging" commit.

### 3.1 — `structlog` is declared as a dependency but never used

`pyproject.toml` lists `structlog>=23.2.0` but every module uses `print()`. This is a clear intent that was never followed through. Every `print("event", ...)` should become `logger.info("event", ...)` with keyword fields.

```python
# Before
print("batch_processed", f"video_id={self.video_id}", f"batch_id={batch_id}")

# After
log.info("batch_processed", video_id=self.video_id, batch_id=batch_id, comments_count=len(processed_comments))
```

### 3.2 — `structlog` should be configured once at the application entry point

Configure a shared renderer (JSON in production, colored console in development) in `main.py` or a dedicated `logging_config.py`. Each module then just calls `structlog.get_logger(__name__)`.

### 3.3 — Go server uses `fmt.Println` and `log.Fatal` with no structure

**File:** `server/main.go`

The Go server should use a structured logger (`log/slog` from the standard library since Go 1.21, or `zerolog`). Every `fmt.Println("Error ...", err)` should carry the error as a field, not a string-concatenated message.

### 3.4 — No request-level logging on the Go server

The Fiber app has no logging middleware. There is no record of which clients connected, how long SSE streams ran, or how many events were emitted. Add `fiber/middleware/logger` or a custom structured middleware.

---

## Phase 4 — Dependency Injection & Architecture Cleanup
> **Goal:** Eliminate global state and module-level side effects so the code is testable and the dependencies of each component are explicit.
> **Commit scope:** One commit per module.

### 4.1 — `KafkaProducer` is instantiated at module import time

**File:** `YTComments/CommentCollector.py`, line 11

```python
# Module-level — runs the moment this file is imported
producer = KafkaProducer(bootstrap_servers='localhost:9092', ...)
```

This means:
- Importing the module tries to connect to Kafka immediately, even in tests.
- The address is hardcoded (see 2.2).
- The producer cannot be replaced or configured by callers.

`KafkaProducer` should be constructed in `CommentsCollector.__init__` and the bootstrap servers read from config.

### 4.2 — TODO comment confirms the producer should be injected — it never was

There are two TODOs in `CommentCollector.py` (lines 9 and 32):
```
# TODO: pass kafka producer instance from outside : collector currently uses it directly
```
This is the right idea. The producer should be passed in as a constructor argument, or a factory function should be injected, so tests can substitute a fake producer.

### 4.3 — `SentimentCollector` uses `async def` but Spark Streaming is synchronous

**File:** `sparkAnalysis/SentimentCollector.py`

`process_video_stream`, `stop_video_stream`, and `stop_all_streams` are all `async def` but they call synchronous Spark and MongoDB operations without running them in a thread pool. The `await processor.start_processing()` call won't yield control during the Spark setup — it just happens to work because `start_processing` launches a background Spark thread internally. This is confusing and fragile. Either go fully synchronous (the Spark layer is already threaded) or properly offload blocking calls to `asyncio.get_event_loop().run_in_executor(...)`.

### 4.4 — `Comment` class silently sets `is_live = False` if the API call fails

**File:** `YTComments/Comment.py`, `get_live_chat_id` method

If the API returns a non-200, `get_live_chat_id` prints an error but still returns `None`. The calling code in `CommentsCollector._collection_loop` then silently skips the video with the message "not live streaming anymore" — which is misleading when the issue is actually an API error. The two failure modes (video ended vs. API error) must be distinguished.

### 4.5 — `YTVideo/main.py` runs `subprocess` and starts the stream at import time

Everything in `YTVideo/main.py` (the `subprocess.check_output` call and all the `sio`/`app` setup) runs at module level. There is no `main()` function. You cannot import this module for testing without triggering a subprocess. Move all startup logic inside `if __name__ == "__main__":` or a `main()` function.

### 4.6 — `sparkAnalysis/SentimentCollector.py` passes `os.getenv(...)` directly to Spark config

If `MONGODB_URI` is not set, `None` is passed to `.config(...)`, which may cause an obscure Spark error instead of a clear startup failure. All required env vars should be validated on startup and raise `ValueError` with a descriptive message.

---

## Phase 5 — Error Handling & Resilience
> **Goal:** Make each service capable of recovering from transient failures without human intervention.
> **Commit scope:** One commit per concern.

### 5.1 — No retry logic on YouTube API calls

**File:** `YTComments/Comment.py`

The `get_stream_details` and `get_live_chat_messages` methods return `None` on any non-200. There is no retry with backoff. YouTube's API regularly returns 429 (rate limit) or transient 5xx errors. These should be retried with exponential backoff (e.g. `tenacity` library or a manual loop with `asyncio.sleep`).

### 5.2 — No retry logic on Kafka produce

**File:** `YTComments/CommentCollector.py`

`producer.send(...)` can fail if the broker is temporarily unavailable. `kafka-python` has built-in retry config (`retries`, `retry_backoff_ms`) that should be set explicitly rather than relying on defaults.

### 5.3 — No dead-letter handling for failed Spark batches

**File:** `sparkAnalysis/SentimentProcessor.py`, `process_batch`

When `insert_many` fails (e.g. MongoDB is down), the entire batch is dropped silently. For a production pipeline, failed batches should either be retried or written to a dead-letter topic in Kafka so they can be replayed.

### 5.4 — Go server does not ping MongoDB before starting

**File:** `server/main.go`

After `mongo.Connect(...)`, the driver does not immediately verify connectivity. Call `client.Ping(ctx, nil)` before starting the HTTP server so a misconfigured MongoDB URI fails fast with a clear error rather than only failing when the first SSE client connects.

### 5.5 — Go SSE stream uses `context.Background()` with no cancellation

**File:** `server/main.go`, inside the `/stream` handler

The change stream uses `context.Background()` forever. If the client disconnects, the stream goroutine keeps running until the process exits. The handler should use the request context (`c.Context()`) so the change stream is cancelled when the client disconnects, preventing goroutine leaks.

### 5.6 — No graceful shutdown on the Go server

**File:** `server/main.go`

`log.Fatal(app.Listen(":3000"))` has no signal handling. Pressing Ctrl-C or sending `SIGTERM` (as Kubernetes does during pod termination) will force-kill active SSE connections. Wrap with `os/signal` and call `app.Shutdown()`.

### 5.7 — `asyncio.gather` in `_collection_loop` uses `return_exceptions=True` but exceptions are ignored

**File:** `YTComments/CommentCollector.py`, line 29

```python
await asyncio.gather(*tasks, return_exceptions=True)
```

`return_exceptions=True` means exceptions are returned as values rather than raised. The return value of `gather` is never inspected — exceptions from individual video tasks are silently swallowed.

---

## Phase 6 — Infrastructure & Docker
> **Goal:** Make every service containerizable with a single command and ready for a cloud deployment.
> **Commit scope:** One "infra" commit, or separate Dockerfile commits per service.

### 6.1 — No Dockerfile for any Python service

There are no `Dockerfile`s for `YTComments`, `sparkAnalysis`, or `YTVideo`. The project cannot be deployed without them. Each service needs its own `Dockerfile` (or a multi-stage one at the root using build targets).

### 6.2 — No Dockerfile for the Go server

`server/main.go` has no `Dockerfile`. Given Go's static binary capability, a two-stage Dockerfile (builder + `gcr.io/distroless/static`) would produce a minimal, secure image.

### 6.3 — MongoDB is not in `docker-compose.yml`

The Python Spark service and Go server both need MongoDB, but `docker-compose.yml` has no MongoDB service. Anyone running `docker compose up` gets Kafka and Spark but no MongoDB.

### 6.4 — Spark uses the `latest` image tag

```yaml
image: bitnami/spark:latest
```

`latest` is non-deterministic — a `docker compose pull` six months from now may break the build. Pin to a specific version (e.g. `bitnami/spark:3.5.3`).

### 6.5 — `version: '3'` is deprecated in Compose

The `version:` key was deprecated in Compose Specification v2. Remove it; modern Docker Compose ignores it but it generates warnings.

### 6.6 — No health checks on any service

None of the Compose services define `healthcheck:`. Dependent services start before their dependencies are ready. For example, the Kafka broker can take 15–30 seconds to be ready for connections — services that start immediately will fail and need to be restarted manually. Add health checks so `depends_on` can use `condition: service_healthy`.

### 6.7 — No restart policies on critical services

Only `kafka-ui` has `restart: always`. Zookeeper, the broker, and Spark have no restart policy. A crash requires manual intervention.

### 6.8 — The Python project and the Go server have no shared network definition

The Go server is run outside Docker Compose (no service entry), so it connects to MongoDB directly. Once services are containerized, they need to share a Docker network and MongoDB needs a published port or the Go server needs a Compose service entry.

---

## Phase 7 — Testing
> **Goal:** Establish a baseline of testability. The architecture currently makes this very hard (global state, no DI) — fixing Phase 4 is a prerequisite.
> **Commit scope:** One commit per module's test file.

### 7.1 — Zero tests exist

There are no test files anywhere. There is no test runner configured in `pyproject.toml`. There is no Go test file.

### 7.2 — What to test first (priority order)

| Priority | Target | Test type | Why |
|---|---|---|---|
| 1 | `SentimentProcessor.analyze_sentiment` | Unit | Pure function, no dependencies |
| 2 | `SentimentProcessor._classify_sentiment` | Unit | Edge cases at ±0.05 boundary |
| 3 | `Comment.get_live_chat_id` | Unit (mock HTTP) | Core path, API response parsing |
| 4 | `CommentsCollector._collect_video_comments` | Unit (mock Kafka) | After DI fix in Phase 4 |
| 5 | `SentimentProcessor.process_batch` | Unit (mock MongoDB) | After DI fix in Phase 4 |
| 6 | Go `/stream` SSE endpoint | Integration | SSE output format correctness |

### 7.3 — Add `pytest` and `pytest-asyncio` to `pyproject.toml`

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-mock>=3.12",
]
```

### 7.4 — Add `go test` coverage for the Go server

The Go server has no `*_test.go` files. At minimum, the SSE message format and MongoDB change stream decoding logic should be tested with `httptest`.

---

## Phase 8 — CI/CD & Documentation
> **Goal:** Automate quality gates and make the project navigable for contributors.
> **Commit scope:** One or two commits.

### 8.1 — No CI/CD pipeline exists

There is no `.github/workflows/`, `.gitlab-ci.yml`, or equivalent. A minimal pipeline should:
1. Lint Python (`ruff`)
2. Type-check Python (`mypy` or `pyright`)
3. Run Python tests (`pytest`)
4. Build Go binary (`go build ./...`)
5. Run Go tests (`go test ./...`)
6. Build Docker images (optional, on push to main)

### 8.2 — No README.md in `etl-live-stream-youtube`

There is no documentation explaining:
- What the project does
- How to set it up (env vars, Docker, YouTube API key prerequisites)
- How to run each service
- The expected data flow

### 8.3 — Add `ruff` and `mypy` to `pyproject.toml`

```toml
[tool.ruff]
line-length = 100
select = ["E", "F", "I", "UP"]

[tool.mypy]
strict = true
```

Type annotations are partially present (`Dict[str, SentimentProcessor]` in `SentimentCollector`) but inconsistent. Adding `mypy` in strict mode would have caught the `comment.snippet.displayMessage` bug (Phase 1.1) at development time.

### 8.4 — TODO comments should become tracked issues

There are 6 TODO comments in the Python codebase. In their current form they will never be addressed. Each should become a GitHub issue (or be fixed in one of the phases above, which most of them already are).

---

## Appendix — Issue Severity Matrix

| ID | File | Issue | Severity |
|---|---|---|---|
| 1.1 | `SentimentProcessor.py:27` | Wrong field access — all data silently dropped | **Critical** |
| 1.2 | `CommentCollector.py:22` | Dict mutation during iteration — runtime crash | **Critical** |
| 2.2 | `CommentCollector.py:11`, `SentimentProcessor.py:47` | Hardcoded Kafka address — broken in Docker | **Critical** |
| 1.3 | `CommentCollector.py:13` | Task garbage collected before running | **High** |
| 1.4 | `SentimentProcessor.py:48` | Exception variable never logged | **High** |
| 4.1 | `CommentCollector.py:11` | Module-level Kafka connection | **High** |
| 5.5 | `server/main.go` | Goroutine leak on client disconnect | **High** |
| 2.3 | `Comment.py:4` | API key read before dotenv loads | **High** |
| 5.1 | `Comment.py` | No retry on YouTube API | **Medium** |
| 6.3 | `docker-compose.yml` | MongoDB missing from Compose | **Medium** |
| 4.5 | `YTVideo/main.py` | Module-level side effects | **Medium** |
| 6.1 | — | No Dockerfiles | **Medium** |
| 7.1 | — | No tests | **Medium** |
| 3.1 | All Python | `structlog` unused, all `print()` | **Low** |
| 6.4 | `docker-compose.yml` | `latest` Spark image tag | **Low** |
| 2.7 | `YTVideo/main.py` | `youtube-dl` end-of-life | **Low** |
| 8.1 | — | No CI/CD | **Low** |
