package main

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"

	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/cors"
	"github.com/joho/godotenv"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

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

	clientOptions := options.Client().ApplyURI(MONGO_URI)
	client, err := mongo.Connect(context.Background(), clientOptions)
	if err != nil {
		slog.Error("mongodb_connect_error", "error", err)
		os.Exit(1)
	}
	slog.Info("mongodb_connected")

	collection := client.Database(DB_NAME).Collection(COLLECTION_NAME)

	app.Get("/stream", func(c *fiber.Ctx) error {

		c.Set("Content-Type", "text/event-stream")
		c.Set("Cache-Control", "no-cache")
		c.Set("Connection", "keep-alive")

		c.Context().SetBodyStreamWriter(func(w *bufio.Writer) {

			changeStream, err := collection.Watch(context.Background(), mongo.Pipeline{})
			if err != nil {
				slog.Error("change_stream_create_error", "error", err)
				return
			}
			defer changeStream.Close(context.Background())

			for changeStream.Next(context.Background()) {
				var change bson.M
				if err := changeStream.Decode(&change); err != nil {
					slog.Error("change_stream_decode_error", "error", err)
					continue
				}

				if change["operationType"] == "insert" {
					doc := change["fullDocument"].(bson.M)

					data, err := json.Marshal(doc)
					if err != nil {
						slog.Error("document_encode_error", "error", err)
						continue
					}

					message := fmt.Sprintf("data: %s\n\n", data)

					if _, err := w.Write([]byte(message)); err != nil {
						slog.Error("stream_write_error", "error", err)
						return
					}

					if err := w.Flush(); err != nil {
						slog.Error("stream_flush_error", "error", err)
						return
					}
				}
			}

			if err := changeStream.Err(); err != nil {
				slog.Error("change_stream_error", "error", err)
			}
		})

		return nil
	})

	if err := app.Listen(":3000"); err != nil {
		slog.Error("server_listen_error", "error", err)
		os.Exit(1)
	}
}
