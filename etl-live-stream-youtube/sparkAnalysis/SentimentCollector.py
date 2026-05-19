"""
Real-time sentiment analysis service for processing YouTube comments using Spark Streaming,
Kafka, and MongoDB.
"""
import os
from typing import Dict

import structlog
from pyspark.sql import SparkSession
from pymongo import MongoClient
from pymongo.collection import Collection

from .SentimentProcessor import SentimentProcessor

log = structlog.get_logger(__name__)



class SentimentCollector:
    def __init__(self):
        # Initialize Spark session
        self.spark = (
            SparkSession.builder
            .appName("YouTubeCommentsSentimentAnalysis")
            .config("spark.streaming.stopGracefullyOnShutdown", True)
            .config("spark.mongodb.output.uri", os.getenv("MONGO_URI"))
            .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.13:3.5.0")
            .config("spark.sql.streaming.forceDeleteTempCheckpointLocation", True)
            .getOrCreate()
        )

        # Initialize MongoDB client
        self.mongo_client = MongoClient(os.getenv("MONGO_URI"))
        self.db = self.mongo_client[os.getenv("DB_NAME", "youtube_sentiment")]
        self.base_collection = os.getenv("COLLECTION_NAME", "comments")

        # Store video processors
        self.video_processors: Dict[str, SentimentProcessor] = {}

        log.info("sentiment_processor_initialized")

    def get_collection(self, video_id: str) -> Collection:
        """Get or create MongoDB collection for a specific video"""
        collection_name = f"{self.base_collection}_{video_id}"
        return self.db[collection_name]

    def process_video_stream(self, video_id: str):
        """Start sentiment analysis for a specific video stream"""
        if video_id in self.video_processors:
            log.warning("stream_already_exists", video_id=video_id)
            return

        try:
            collection = self.get_collection(video_id)
            processor = SentimentProcessor(video_id, self.spark, collection)
            self.video_processors[video_id] = processor
            processor.start_processing()

        except Exception as e:
            log.error("video_processing_error", video_id=video_id, error=str(e))
            self.stop_video_stream(video_id)
            raise

    def stop_video_stream(self, video_id: str):
        """Stop sentiment analysis for a specific video stream"""
        processor = self.video_processors.get(video_id)
        if processor:
            processor.stop_processing()
            del self.video_processors[video_id]
            log.info("video_stream_stopped", video_id=video_id)

    def stop_all_streams(self):
        """Stop all video streams and cleanup resources"""
        for video_id in list(self.video_processors.keys()):
            self.stop_video_stream(video_id)

        if self.spark:
            self.spark.stop()

        if self.mongo_client:
            self.mongo_client.close()

        log.info("all_streams_stopped")
