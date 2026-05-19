import os

import structlog
from nltk.sentiment.vader import SentimentIntensityAnalyzer
from pymongo.errors import ConnectionFailure
from pyspark.sql.functions import col, from_json
from pyspark.sql.types import StringType, StructField, StructType, TimestampType
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

log = structlog.get_logger(__name__)

_DEAD_LETTER_TOPIC = "dead_letter_comments"


def _log_mongo_retry(retry_state) -> None:
    log.warning(
        "mongo_insert_retry",
        attempt=retry_state.attempt_number,
        exception=str(retry_state.outcome.exception()),
    )


class SentimentProcessor:
    def __init__(self, video_id, spark, mongodb_collection, dead_letter_producer=None):
        self.video_id = video_id
        self.spark = spark
        self.collection = mongodb_collection
        self.dead_letter_producer = dead_letter_producer
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

    @retry(
        retry=retry_if_exception_type(ConnectionFailure),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
        before_sleep=_log_mongo_retry,
    )
    def _insert_many(self, documents):
        self.collection.insert_many(documents)

    def _send_to_dead_letter(self, documents, batch_id):
        if self.dead_letter_producer is None:
            log.error(
                "batch_dropped_no_dead_letter_producer",
                video_id=self.video_id,
                batch_id=batch_id,
                count=len(documents),
            )
            return
        try:
            self.dead_letter_producer.send(
                _DEAD_LETTER_TOPIC,
                value={"batch_id": batch_id, "video_id": self.video_id, "documents": documents},
            )
            self.dead_letter_producer.flush()
            log.warning(
                "batch_dead_lettered",
                video_id=self.video_id,
                batch_id=batch_id,
                count=len(documents),
            )
        except Exception as e:
            log.error(
                "dead_letter_send_failed",
                video_id=self.video_id,
                batch_id=batch_id,
                error=str(e),
            )

    def process_batch(self, batch_df, batch_id):
        """Process and store a batch of comments"""
        try:
            comments = batch_df.collect()
            if not comments:
                return

            processed_comments = []
            for comment in comments:
                sentiment_scores = self.analyze_sentiment(comment.comment)
                processed_comments.append({
                    "video_id": self.video_id,
                    "author": comment.author_name,
                    "comment": comment.comment,
                    "profile_image": comment.profile_image,
                    "published_at": comment.published_at,
                    "sentiment": sentiment_scores,
                    "batch_id": batch_id,
                })

            if not processed_comments:
                return

            try:
                self._insert_many(processed_comments)
                log.info(
                    "batch_processed",
                    video_id=self.video_id,
                    batch_id=batch_id,
                    comments_count=len(processed_comments),
                )
            except Exception as e:
                log.error(
                    "batch_insert_failed",
                    video_id=self.video_id,
                    batch_id=batch_id,
                    error=str(e),
                )
                self._send_to_dead_letter(processed_comments, batch_id)

        except Exception as e:
            log.error(
                "batch_processing_error",
                video_id=self.video_id,
                batch_id=batch_id,
                error=str(e),
            )

    def start_processing(self):
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
                .option(
                    "kafka.bootstrap.servers",
                    os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
                )
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

            log.info("stream_started", video_id=self.video_id)

        except Exception as e:
            log.error("stream_start_error", video_id=self.video_id, error=str(e))
            raise

    def stop_processing(self):
        """Stop processing the video's comment stream"""
        if self.streaming_query:
            self.streaming_query.stop()
            log.info("stream_stopped", video_id=self.video_id)
