"""
Entry point for running the Spark Analysis service that processes YouTube comments
and performs sentiment analysis.
"""
import asyncio
import os
from dotenv import load_dotenv

from .SentimentCollector import SentimentCollector
import nltk

# Load environment variables
load_dotenv()

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
        print(f"Starting sentiment analysis for video: {video_id}")
        await collector.process_video_stream(video_id)
        await asyncio.sleep(2)  # Small delay between starting each stream

    try:
        # Keep the main task running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down sentiment analysis gracefully...")
        await collector.stop_all_streams()

def main():
    print("Starting Spark Sentiment Analysis Service...")
    asyncio.run(run())

if __name__ == "__main__":
    main()
