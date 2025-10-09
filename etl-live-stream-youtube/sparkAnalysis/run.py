"""
Entry point for running the Spark Analysis service that processes YouTube comments
and performs sentiment analysis.
"""
import asyncio
from dotenv import load_dotenv
from sparkAnalysis.main import SentimentProcessor

# Load environment variables
load_dotenv()

async def run():
    # Initialize the sentiment processor
    processor = SentimentProcessor()

    # List of video IDs to analyze (should match the ones in YTComments)
    video_ids = ["lLTEkaB8l1A" , "_MXcIddl6eA" , "wkyXiX5Fc6E"]

    # Start processing for each video
    for video_id in video_ids:
        print(f"Starting sentiment analysis for video: {video_id}")
        await processor.process_video_stream(video_id)
        await asyncio.sleep(2)  # Small delay between starting each stream

    try:
        # Keep the main task running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down sentiment analysis gracefully...")
        await processor.stop_all_streams()

def main():
    print("Starting Spark Sentiment Analysis Service...")
    asyncio.run(run())

if __name__ == "__main__":
    main()
