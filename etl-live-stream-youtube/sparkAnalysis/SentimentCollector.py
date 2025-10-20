"""
Real-time sentiment analysis service for processing YouTube comments using Spark Streaming,
Kafka, and MongoDB.
"""
import os
from typing import Dict
from dotenv import load_dotenv
from pyspark.sql import SparkSession
from pymongo import MongoClient
from pymongo.collection import Collection

from .SentimentProcessor import SentimentProcessor

# Load environment variables
load_dotenv()



class SentimentCollector:
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
        self.video_processors: Dict[str, SentimentProcessor] = {}

        print("sentiment_processor_initialized")

    def get_collection(self, video_id: str) -> Collection:
        """Get or create MongoDB collection for a specific video"""
        collection_name = f"{self.base_collection}_{video_id}"
        return self.db[collection_name]

    async def process_video_stream(self, video_id: str):
        """Start sentiment analysis for a specific video stream"""
        if video_id in self.video_processors:
            print("stream_already_exists:",video_id)
            return

        try:
            collection = self.get_collection(video_id)
            processor = SentimentProcessor(video_id, self.spark, collection)
            self.video_processors[video_id] = processor
            await processor.start_processing()

        except Exception as e:
            print("video_processing_error",e)
            await self.stop_video_stream(video_id)
            raise

    async def stop_video_stream(self, video_id: str):
        """Stop sentiment analysis for a specific video stream"""
        processor = self.video_processors.get(video_id)
        if processor:
            await processor.stop_processing()
            del self.video_processors[video_id]
            print("video_stream_stopped",video_id)

    async def stop_all_streams(self):
        """Stop all video streams and cleanup resources"""
        for video_id in list(self.video_processors.keys()):
            await self.stop_video_stream(video_id)

        if self.spark:
            self.spark.stop()

        if self.mongo_client:
            self.mongo_client.close()

        print("all_streams_stopped")
