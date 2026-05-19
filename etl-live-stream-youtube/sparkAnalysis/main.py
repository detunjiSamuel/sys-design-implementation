"""
Entry point for running the Spark Analysis service that processes YouTube comments
and performs sentiment analysis.
"""
import asyncio
import os

import structlog
from dotenv import load_dotenv

from .SentimentCollector import SentimentCollector
from logging_config import configure_logging
import nltk

log = structlog.get_logger(__name__)

# Download VADER lexicon for sentiment analysis : nltk caches it locally
nltk.download("vader_lexicon")

async def run():
    # Initialize the sentiment processor
    collector = SentimentCollector()

    video_ids = [v.strip() for v in os.getenv("VIDEO_IDS", "").split(",") if v.strip()]
    if not video_ids:
        raise ValueError("VIDEO_IDS environment variable is not set or empty")

    # Start processing for each video
    for video_id in video_ids:
        log.info("starting_video_analysis", video_id=video_id)
        await collector.process_video_stream(video_id)
        await asyncio.sleep(2)  # Small delay between starting each stream

    try:
        # Keep the main task running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        log.info("shutdown")
        await collector.stop_all_streams()

def main():
    load_dotenv()
    configure_logging()
    log.info("service_starting")
    asyncio.run(run())

if __name__ == "__main__":
    main()
