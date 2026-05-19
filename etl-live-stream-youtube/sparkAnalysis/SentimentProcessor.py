import os

from nltk.sentiment.vader import SentimentIntensityAnalyzer
from pyspark.sql.types import (
    FloatType,
    StructType,
    StructField,
    StringType,
    TimestampType
)

from pyspark.sql.functions import col, from_json

class SentimentProcessor:
    def __init__(self, video_id, spark, mongodb_collection):
        self.video_id = video_id
        self.spark = spark
        self.collection = mongodb_collection
        self.streaming_query = None
        self.vader = SentimentIntensityAnalyzer()

    def _classify_sentiment(self, compound_score):
        """Classify sentiment based on VADER compound score"""
        if compound_score >= 0.05:
            return "positive"
        elif compound_score <= -0.05:
            return "negative"
        return "neutral"

    def analyze_sentiment(self, text):
        """Analyze sentiment of text using VADER"""
        scores = self.vader.polarity_scores(text)
        return {
            "compound": scores["compound"],
            "classification": self._classify_sentiment(scores["compound"]),
            "pos": scores["pos"],
            "neg": scores["neg"],
            "neu": scores["neu"]
        }

    def process_batch(self, batch_df, batch_id):
        """Process and store a batch of comments"""
        try:
            comments = batch_df.collect()
            if not comments:
                return

            processed_comments = []
            for comment in comments:

                sentiment_scores = self.analyze_sentiment(comment.comment)

                processed_comment = {
                    "video_id": self.video_id,
                    "author": comment.author_name,
                    "comment": comment.comment,
                    "profile_image": comment.profile_image,
                    "published_at": comment.published_at,
                    "sentiment": sentiment_scores,
                    "batch_id": batch_id
                }

                processed_comments.append(processed_comment)

            if processed_comments:
                self.collection.insert_many(processed_comments)
                print(
                    "batch_processed",
                    f"video_id={self.video_id}",
                    f"batch_id={batch_id}",
                    f"comments_count={len(processed_comments)}"
                )

        except Exception as e:
            print(
                "batch_processing_error",
                f"video_id={self.video_id}",
                f"batch_id={batch_id}",
                f"error={e}"
            )

    async def start_processing(self):
        """Start processing the video's comment stream"""
        try:
            # Define schema for incoming comments
            comment_schema = StructType([
                StructField("comment", StringType(), True),
                StructField("profile_image", StringType(), True),
                StructField("author_name", StringType(), True),
                StructField("published_at", TimestampType(), True)
            ])

            # Create streaming DataFrame from Kafka
            stream_df = (
                self.spark.readStream
                .format("kafka")
                .option("kafka.bootstrap.servers", os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"))
                .option("subscribe", f"comments_{self.video_id}")
                .option("startingOffsets", "latest")
                .load()
            )

            # Parse JSON data
            parsed_df = stream_df.select(
                from_json(col("value").cast("string"), comment_schema).alias("data")
            ).select("data.*")

            # Start streaming query
            self.streaming_query = (
                parsed_df.writeStream
                .foreachBatch(self.process_batch)
                .trigger(processingTime="1 second")
                .outputMode("append")
                .start()
            )

            print("stream_started",self.video_id)

        except Exception as e:
            print("stream_start_error",self.video_id, e)
            raise

    async def stop_processing(self):
        """Stop processing the video's comment stream"""
        if self.streaming_query:
            self.streaming_query.stop()
            print("stream_stopped",self.video_id)
