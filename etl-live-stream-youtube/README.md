# etl-live-stream-youtube

**Real-time sentiment analysis pipeline for YouTube live-chat comments — built to learn stream processing, Kafka, and SSE. Not for prod.**

---

## Services

| Service | Language | Role |
|---|---|---|
| `YTComments` | Python | Polls YouTube Data API for live-chat messages, publishes to Kafka |
| `sparkAnalysis` | Python / PySpark | Reads from Kafka, scores sentiment with VADER, writes to MongoDB |
| `server` | Go | Tails MongoDB change stream, pushes inserts to browser as SSE |

Infrastructure: **Kafka + Zookeeper** (message bus), **MongoDB** (store + change stream source), **Spark** (stream processor).

---

<details>
<summary><strong>How to run</strong>  click to expand (just ask an AI, honestly)</summary>

**Prerequisites:** Docker, a YouTube Data API v3 key, video IDs of active live streams.

```bash
# 1 — copy and fill in secrets
cp .env.example .env

# 2 — start infrastructure + Go server
docker compose up -d

# 3 — start comment collector
VIDEO_IDS=<id1>,<id2> uv run python -m YTComments.main

# 4 — start sentiment processor
VIDEO_IDS=<id1>,<id2> uv run python -m sparkAnalysis.main
```

The SSE stream is available at `http://localhost:3000/stream`.  
Kafka UI is at `http://localhost:7777`.

**Required env vars** (see `.env.example`):

```
YT_API_KEY=
VIDEO_IDS=
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
MONGO_URI=mongodb://localhost:27017
DB_NAME=youtube_sentiment
COLLECTION_NAME=comments
```

</details>

---

## Architecture — detailed notes (for me , not you)

### How to describe it in one paragraph

"end-to-end streaming pipeline that takes YouTube live-chat comments and scores their sentiment in near-real time. A Python service polls the YouTube Data API and publishes each comment as a JSON message to a Kafka topic — one topic per video. A Spark Structured Streaming job consumes those topics, runs VADER sentiment analysis on each micro-batch, and writes the enriched documents to MongoDB. On the serving side, a Go HTTP server opens a MongoDB change stream so it gets notified the instant a new document lands, and it forwards that as a Server-Sent Event to whatever browser is connected. The main architectural choices were: Kafka to decouple the collector from the processor so either can restart without losing data; Spark for the processing layer because I wanted hands-on experience with its streaming API; MongoDB because its change stream lets me avoid polling and keep the push model all the way to the client; and Go for the SSE server because goroutines are cheap for many concurrent long-lived connections."

---

### Data flow

```
YouTube API
    │  HTTP polling (requests + tenacity retries)
    ▼
YTComments service  ──►  Kafka topic: comments_{video_id}
                                │
                                │  Spark Structured Streaming
                                │  (kafka-sql connector, 1-second micro-batch)
                                ▼
                         sparkAnalysis service
                                │  VADER sentiment scoring per comment
                                │  insert_many → MongoDB collection comments_{video_id}
                                ▼
                            MongoDB
                                │  change stream (watch for inserts)
                                ▼
                          Go SSE server  ──►  Browser / frontend
```

---

### Why Kafka as the transport layer

The collector and the Spark processor run at different speeds and can fail independently. Kafka decouples them: if Spark restarts, it can replay from the last committed offset rather than losing the gap. Without Kafka you would need the collector to buffer in memory or write directly to MongoDB, which couples the two services and makes replay impossible.

Each video gets its own topic (`comments_{video_id}`) so Spark can open a separate streaming query per video, each with independent offset tracking.

---

### Why Spark Structured Streaming

Spark was chosen deliberately over simpler alternatives (e.g., a plain consumer loop writing to Mongo) to learn the streaming API. The relevant design points:

- **`foreachBatch`** — rather than using a Spark sink directly, `foreachBatch` hands each micro-batch as a regular DataFrame to Python code. This makes it easy to call the VADER scorer (which is not a Spark UDF) and to call `insert_many` with MongoDB.
- **1-second trigger** — small enough to feel real-time, large enough to batch inserts.
- **Schema declaration** — the Kafka value is raw bytes; Spark uses `from_json` with an explicit `StructType` to parse the payload into typed columns. This fails fast if the producer changes the payload shape.
- **`startingOffsets: latest`** — on startup the processor only reads new messages, not the full topic history.

---

### Sentiment analysis — VADER

VADER (`vaderSentiment` / `nltk`) is a rule-based, lexicon-driven analyser specifically tuned for short social media text. It outputs four scores: `pos`, `neg`, `neu`, and a `compound` score in [-1, 1]. The `compound` threshold used here is ±0.05 (standard VADER guidance):

- `compound >= 0.05` → positive
- `compound <= -0.05` → negative
- otherwise → neutral

The reasons for choosing VADER over a transformer model:
1. No GPU, no model download, no inference latency — runs in the same Python process as Spark.
2. Handles emoji, ALL-CAPS, and punctuation emphasis (common in live chat) natively.
3. Deterministic output — useful for reproducibility during learning.

---

### Why MongoDB and change streams

MongoDB was chosen because:
1. **Schema flexibility** — each comment document carries a nested `sentiment` sub-document with five fields; there is no fixed relational schema to maintain.
2. **Change streams** — MongoDB's change stream API lets the Go server `Watch` a collection and receive a notification for every new insert without polling. This is the mechanism that makes the SSE stream truly push-based end-to-end.

Each video's comments land in a separate collection (`comments_{video_id}`) so queries can be scoped by video without an index on `video_id` being mandatory.

---

### Go SSE server design

The server is in Go rather than Python because Go handles many concurrent, long-lived HTTP connections cheaply via goroutines (each SSE client is one goroutine blocked on the MongoDB change stream).

Key design decisions in the server:

- **`ChangeWatcher` interface** — instead of taking a `*mongo.ChangeStream` directly, the stream handler accepts a `ChangeWatcher` interface (`Next`, `Decode`, `Close`, `Err`). This is the standard Go testability pattern: the real handler uses the live MongoDB change stream; tests inject a mock. This is why the Go tests exist and do not need a running database.
- **Context cancellation** — the handler derives a `context.WithCancel` from the Fiber request context. When the client disconnects, Fiber cancels the request context, which propagates into `changeStream.Next(ctx)`, causing it to return `false` and exit cleanly. Without this, the goroutine would block forever — a goroutine leak.
- **SSE format** — the wire format is `data: <json>\n\n`. The `\n\n` is mandatory per the SSE spec; it marks the end of an event. The browser's `EventSource` API parses this automatically.
- **Graceful shutdown** — the server listens for `SIGTERM`/`SIGINT` and calls `app.Shutdown()` before disconnecting MongoDB. This matters for Kubernetes: during a rolling deploy, the pod receives `SIGTERM` before being removed from the load balancer; a hard kill would drop active SSE connections.
- **Structured logging with `log/slog`** — stdlib since Go 1.21. Each log line is JSON emitted to stderr, with fields (`ip`, `latency_ms`, `events_emitted`) instead of a concatenated string. This is what log aggregators (Datadog, CloudWatch Logs Insights, Loki) parse.

---

### Retry strategy

Both the Python and Go layers implement explicit retry with exponential backoff:

| Layer | Library | Retried errors | Max attempts |
|---|---|---|---|
| YouTube API calls | `tenacity` | 429, 5xx | 5 |
| MongoDB `insert_many` | `tenacity` | `ConnectionFailure` | 3 |

If `insert_many` exhausts retries, the batch is forwarded to a Kafka dead-letter topic (`dead_letter_comments`) rather than silently dropped. This allows replay once MongoDB recovers.

---

### Libraries at a glance

**Python**

| Library | Why |
|---|---|
| `kafka-python` | Kafka producer in the collector and dead-letter producer in Spark |
| `pyspark` | Spark Structured Streaming engine |
| `vaderSentiment` / `nltk` | Rule-based sentiment scorer tuned for social text |
| `pymongo` | MongoDB client for the Spark layer |
| `requests` | Synchronous HTTP to the YouTube API (issue #2 tracks migrating to `aiohttp`) |
| `tenacity` | Retry with exponential backoff and pluggable retry predicates |
| `structlog` | Structured key=value log output, configurable renderer per environment |
| `python-dotenv` | `.env` loading at the entry point |

**Go**

| Library | Why |
|---|---|
| `gofiber/fiber/v2` | Fast HTTP framework built on `fasthttp`; exposes `SetBodyStreamWriter` for streaming responses |
| `mongo-driver` | Official MongoDB Go driver; provides change stream API |
| `joho/godotenv` | `.env` loading |
| `log/slog` | Structured logging, standard library since Go 1.21 — no external dep needed |
