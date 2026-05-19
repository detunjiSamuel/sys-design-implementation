"""
Entry point for running the Spark Analysis service that processes YouTube comments
and performs sentiment analysis.
"""
import os
import time

import nltk
import structlog
from dotenv import load_dotenv

from logging_config import configure_logging

from .SentimentCollector import SentimentCollector

log = structlog.get_logger(__name__)

# Download VADER lexicon for sentiment analysis : nltk caches it locally
nltk.download("vader_lexicon")

def run():
    collector = SentimentCollector()

    video_ids = [v.strip() for v in os.getenv("VIDEO_IDS", "").split(",") if v.strip()]
    if not video_ids:
        raise ValueError("VIDEO_IDS environment variable is not set or empty")

    for video_id in video_ids:
        log.info("starting_video_analysis", video_id=video_id)
        collector.process_video_stream(video_id)
        time.sleep(2)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("shutdown")
        collector.stop_all_streams()

def main():
    load_dotenv()
    configure_logging()
    log.info("service_starting")
    run()

if __name__ == "__main__":
    main()
