# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM golang:1.24 AS builder

WORKDIR /build

COPY go.mod go.sum ./
RUN go mod download

COPY . .

# Statically-linked binary with debug symbols stripped.
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o server .

# Placeholder .env so godotenv.Load does not exit 1 on startup.
# Real values must be injected via Docker env vars or --env-file at runtime.
RUN touch .env

# ── Stage 2: minimal runtime ──────────────────────────────────────────────────
FROM gcr.io/distroless/static:nonroot

WORKDIR /app

COPY --from=builder /build/server .
COPY --from=builder /build/.env .

EXPOSE 3000

CMD ["/app/server"]
