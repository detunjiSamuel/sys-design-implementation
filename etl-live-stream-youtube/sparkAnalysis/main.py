"""
Real-time sentiment analysis service for processing YouTube comments using Spark Streaming,
Kafka, and MongoDB.
"""
import os
from typing import Dict
import structlog
from dotenv import load_dotenv
from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, col, udf
from pyspark.sql.types import StructType, StructField, StringType
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from pymongo import MongoClient
from pymongo.collection import Collection

# Load environment variables
load_dotenv()

# Configure structured logging
logger = structlog.get_logger()


class VideoSentimentProcessor:
    def __init__(self, video_id: str, spark: SparkSession, mongodb_collection: Collection):
        self.video_id = video_id
        self.spark = spark
        self.collection = mongodb_collection
        self.streaming_query = None
        self.vader = SentimentIntensityAnalyzer()

    def _classify_sentiment(self, compound_score: float) -> str:
        """Classify sentiment based on VADER compound score"""
        if compound_score >= 0.05:
            return "positive"
        elif compound_score <= -0.05:
            return "negative"
        return "neutral"

    def analyze_sentiment(self, text: str) -> dict:
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
                sentiment_scores = self.analyze_sentiment(comment.snippet.displayMessage)
                processed_comment = {
                    "video_id": self.video_id,
                    "author": comment.authorDetails.displayName,
                    "comment": comment.snippet.displayMessage,
                    "profile_image": comment.authorDetails.profileImageUrl,
                    "author_channel_id": comment.authorDetails.channelId,
                    "published_at": comment.snippet.publishedAt,
                    "is_verified": comment.authorDetails.isVerified,
                    "is_chat_owner": comment.authorDetails.isChatOwner,
                    "is_chat_sponsor": comment.authorDetails.isChatSponsor,
                    "is_chat_moderator": comment.authorDetails.isChatModerator,
                    "sentiment": sentiment_scores,
                    "batch_id": batch_id
                }
                processed_comments.append(processed_comment)

            if processed_comments:
                self.collection.insert_many(processed_comments)
                logger.info(
                    "batch_processed",
                    video_id=self.video_id,
                    batch_id=batch_id,
                    comments_count=len(processed_comments)
                )

        except Exception as e:
            logger.error(
                "batch_processing_error",
                video_id=self.video_id,
                batch_id=batch_id,
                error=str(e)
            )

    async def start_processing(self):
        """Start processing the video's comment stream"""
        try:
            # Define schema for incoming comments
            comment_schema = StructType([
                StructField("kind", StringType(), True),
                StructField("etag", StringType(), True),
                StructField("id", StringType(), True),
                StructField("snippet", StructType([
                    StructField("type", StringType(), True),
                    StructField("liveChatId", StringType(), True),
                    StructField("authorChannelId", StringType(), True),
                    StructField("publishedAt", StringType(), True),
                    StructField("hasDisplayContent", StringType(), True),
                    StructField("displayMessage", StringType(), True),
                ]), True),
                StructField("authorDetails", StructType([
                    StructField("channelId", StringType(), True),
                    StructField("channelUrl", StringType(), True),
                    StructField("displayName", StringType(), True),
                    StructField("profileImageUrl", StringType(), True),
                    StructField("isVerified", StringType(), True),
                    StructField("isChatOwner", StringType(), True),
                    StructField("isChatSponsor", StringType(), True),
                    StructField("isChatModerator", StringType(), True)
                ]), True)
            ])

            # Create streaming DataFrame from Kafka
            stream_df = (
                self.spark.readStream
                .format("kafka")
                .option("kafka.bootstrap.servers", "127.0.0.1:9092")
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

            logger.info("stream_started", video_id=self.video_id)

        except Exception as e:
            logger.error("stream_start_error", video_id=self.video_id, error=str(e))
            raise

    async def stop_processing(self):
        """Stop processing the video's comment stream"""
        if self.streaming_query:
            self.streaming_query.stop()
            logger.info("stream_stopped", video_id=self.video_id)


class SentimentProcessor:
    def __init__(self):
        # Initialize Spark session
        self.spark = (
            SparkSession.builder
            .appName("YouTubeCommentsSentimentAnalysis")
            .config("spark.streaming.stopGracefullyOnShutdown", True)
            .config("spark.mongodb.output.uri", os.getenv("MONGODB_URI"))
            .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.13:3.5.0")
            .config("spark.sql.streaming.forceDeleteTempCheckpointLocation", True)
            .getOrCreate()
        )

        # Initialize MongoDB client
        self.mongo_client = MongoClient(os.getenv("MONGODB_URI"))
        self.db = self.mongo_client[os.getenv("DATABASE", "youtube_sentiment")]
        self.base_collection = os.getenv("COLLECTION", "comments")

        # Store video processors
        self.video_processors: Dict[str, VideoSentimentProcessor] = {}

        logger.info("sentiment_processor_initialized")

    def get_collection(self, video_id: str) -> Collection:
        """Get or create MongoDB collection for a specific video"""
        collection_name = f"{self.base_collection}_{video_id}"
        return self.db[collection_name]

    async def process_video_stream(self, video_id: str):
        """Start sentiment analysis for a specific video stream"""
        if video_id in self.video_processors:
            logger.warning("stream_already_exists", video_id=video_id)
            return

        try:
            collection = self.get_collection(video_id)
            processor = VideoSentimentProcessor(video_id, self.spark, collection)
            self.video_processors[video_id] = processor
            await processor.start_processing()

        except Exception as e:
            logger.error("video_processing_error", video_id=video_id, error=str(e))
            await self.stop_video_stream(video_id)
            raise

    async def stop_video_stream(self, video_id: str):
        """Stop sentiment analysis for a specific video stream"""
        processor = self.video_processors.get(video_id)
        if processor:
            await processor.stop_processing()
            del self.video_processors[video_id]
            logger.info("video_stream_stopped", video_id=video_id)

    async def stop_all_streams(self):
        """Stop all video streams and cleanup resources"""
        for video_id in list(self.video_processors.keys()):
            await self.stop_video_stream(video_id)

        if self.spark:
            self.spark.stop()

        if self.mongo_client:
            self.mongo_client.close()

        logger.info("all_streams_stopped")
