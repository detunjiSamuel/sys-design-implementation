package main

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"

	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/cors"
	"github.com/joho/godotenv"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

func main() {
	fmt.Println("Hello, World!")

	err := godotenv.Load(".env")

	if err != nil {
		fmt.Println("Error loading .env file")
		return
	}

	MONGO_URI := os.Getenv("MONGO_URI")
	DB_NAME := os.Getenv("DB_NAME")
	COLLECTION_NAME := os.Getenv("COLLECTION_NAME")

	app := fiber.New()

	app.Use(cors.New())

	clientOptions := options.Client().ApplyURI(MONGO_URI)
	client, err := mongo.Connect(context.Background(), clientOptions)

	if err != nil {
		fmt.Println("MongoDB connection error:", err)
		return
	}
	fmt.Println("Connected to MongoDB!")

	collection := client.Database(DB_NAME).Collection(COLLECTION_NAME)

	app.Get("/stream", func(c *fiber.Ctx) error {

		c.Set("Content-Type", "text/event-stream")
		c.Set("Cache-Control", "no-cache")
		c.Set("Connection", "keep-alive")

		c.Context().SetBodyStreamWriter(func(w *bufio.Writer) {

			changeStream, err := collection.Watch(context.Background(), mongo.Pipeline{})

			if err != nil {
				fmt.Println("Error creating change stream:", err)
				return
			}
			defer changeStream.Close(context.Background())

			for changeStream.Next(context.Background()) {
				var change bson.M
				if err := changeStream.Decode(&change); err != nil {
					fmt.Println("Error decoding change stream document:", err)
					continue
				}

				if change["operationType"] == "insert" {
					doc := change["fullDocument"].(bson.M)

					data, err := json.Marshal(doc)
					if err != nil {
						fmt.Println("Error with encoding document:", err)
						continue
					}

					message := fmt.Sprintf("data: %s\n\n", data)

					if _, err := w.Write([]byte(message)); err != nil {
						fmt.Println("Error writing to stream:", err)
						return
					}

					if err := w.Flush(); err != nil {
						fmt.Println("Error flushing stream:", err)
						return
					}
				}
			}

			if err := changeStream.Err(); err != nil {
				fmt.Println("Change stream error:", err)
			}
		})

		return nil
	})
	log.Fatal(app.Listen(":3000"))

}
