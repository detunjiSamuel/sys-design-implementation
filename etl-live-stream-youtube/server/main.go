package main

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/cors"
	"github.com/joho/godotenv"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

// ChangeWatcher is the minimal interface over *mongo.ChangeStream needed by the
// stream handler. Declaring it here lets tests inject a mock without pulling in
// a real MongoDB connection.
type ChangeWatcher interface {
	Next(ctx context.Context) bool
	Decode(val interface{}) error
	Close(ctx context.Context) error
	Err() error
}

// formatSSEMessage serialises a MongoDB document as a Server-Sent Events data frame.
func formatSSEMessage(doc bson.M) (string, error) {
	data, err := json.Marshal(doc)
	if err != nil {
		return "", err
	}
	return fmt.Sprintf("data: %s\n\n", data), nil
}

// processChangeEvent inspects a raw change-stream document. It returns the SSE
// message to emit and true when the event is an insert that can be forwarded to
// clients; it returns ("", false) for all other cases (non-insert, missing
// fullDocument, serialisation errors).
func processChangeEvent(change bson.M) (string, bool) {
	if change["operationType"] != "insert" {
		return "", false
	}
	doc, ok := change["fullDocument"].(bson.M)
	if !ok {
		return "", false
	}
	msg, err := formatSSEMessage(doc)
	if err != nil {
		return "", false
	}
	return msg, true
}

// newStreamHandler returns a Fiber handler that streams MongoDB change events to
// the client as Server-Sent Events. watchFn is called once per request to open
// the change stream; injecting it makes the handler testable without a live DB.
func newStreamHandler(watchFn func(ctx context.Context) (ChangeWatcher, error)) fiber.Handler {
	return func(c *fiber.Ctx) error {
		c.Set("Content-Type", "text/event-stream")
		c.Set("Cache-Control", "no-cache")
		c.Set("Connection", "keep-alive")

		clientIP := c.IP()
		ctx, cancel := context.WithCancel(c.Context())

		c.Context().SetBodyStreamWriter(func(w *bufio.Writer) {
			defer cancel()

			streamStart := time.Now()
			eventsEmitted := 0
			slog.Info("stream_connected", "ip", clientIP)
			defer func() {
				slog.Info("stream_disconnected",
					"ip", clientIP,
					"duration_ms", time.Since(streamStart).Milliseconds(),
					"events_emitted", eventsEmitted,
				)
			}()

			changeStream, err := watchFn(ctx)
			if err != nil {
				slog.Error("change_stream_create_error", "error", err)
				return
			}
			defer changeStream.Close(ctx)

			for changeStream.Next(ctx) {
				var change bson.M
				if err := changeStream.Decode(&change); err != nil {
					slog.Error("change_stream_decode_error", "error", err)
					continue
				}

				message, shouldEmit := processChangeEvent(change)
				if !shouldEmit {
					continue
				}

				if _, err := w.Write([]byte(message)); err != nil {
					slog.Error("stream_write_error", "error", err)
					return
				}

				if err := w.Flush(); err != nil {
					slog.Error("stream_flush_error", "error", err)
					return
				}

				eventsEmitted++
			}

			if err := changeStream.Err(); err != nil && ctx.Err() == nil {
				slog.Error("change_stream_error", "error", err)
			}
		})

		return nil
	}
}

func requestLogger(c *fiber.Ctx) error {
	start := time.Now()
	err := c.Next()
	slog.Info("request",
		"method", c.Method(),
		"path", c.Path(),
		"status", c.Response().StatusCode(),
		"latency_ms", time.Since(start).Milliseconds(),
		"ip", c.IP(),
	)
	return err
}

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stderr, nil)))

	slog.Info("server_starting")

	err := godotenv.Load(".env")
	if err != nil {
		slog.Error("dotenv_load_error", "error", err)
		os.Exit(1)
	}

	MONGO_URI := os.Getenv("MONGO_URI")
	DB_NAME := os.Getenv("DB_NAME")
	COLLECTION_NAME := os.Getenv("COLLECTION_NAME")

	app := fiber.New()

	app.Use(cors.New())
	app.Use(requestLogger)

	clientOptions := options.Client().ApplyURI(MONGO_URI)
	client, err := mongo.Connect(context.Background(), clientOptions)
	if err != nil {
		slog.Error("mongodb_connect_error", "error", err)
		os.Exit(1)
	}

	pingCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := client.Ping(pingCtx, nil); err != nil {
		slog.Error("mongodb_ping_error", "error", err)
		os.Exit(1)
	}
	slog.Info("mongodb_connected")

	collection := client.Database(DB_NAME).Collection(COLLECTION_NAME)

	watchFn := func(ctx context.Context) (ChangeWatcher, error) {
		return collection.Watch(ctx, mongo.Pipeline{})
	}
	app.Get("/stream", newStreamHandler(watchFn))

	go func() {
		if err := app.Listen(":3000"); err != nil {
			slog.Error("server_listen_error", "error", err)
			os.Exit(1)
		}
	}()

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, os.Interrupt, syscall.SIGTERM)
	<-quit

	slog.Info("server_shutting_down")

	if err := app.Shutdown(); err != nil {
		slog.Error("server_shutdown_error", "error", err)
	}

	disconnectCtx, disconnectCancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer disconnectCancel()
	if err := client.Disconnect(disconnectCtx); err != nil {
		slog.Error("mongodb_disconnect_error", "error", err)
	}

	slog.Info("server_stopped")
}
