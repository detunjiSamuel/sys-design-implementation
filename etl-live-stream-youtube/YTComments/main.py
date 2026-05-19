import asyncio
import os

import structlog
from dotenv import load_dotenv

from YTComments.CommentCollector import CommentsCollector
from logging_config import configure_logging

log = structlog.get_logger(__name__)


# TODOD: make changes to to collector to use asyncio without semaphre:
# reason : they do not really share resors
# TODO : update requests to aihttp reason: there is no reason to block the application while waiting for network response

async def run():
    video_ids = [v.strip() for v in os.getenv("VIDEO_IDS", "").split(",") if v.strip()]
    if not video_ids:
        raise ValueError("VIDEO_IDS environment variable is not set or empty")

    collector = CommentsCollector(max_concurrent_tasks=2)
    for vid in video_ids:
        log.info("adding_video", video_id=vid)
        await collector.add_video(vid)
        await asyncio.sleep(3)

    await collector.start()

    try:
        # Keep the main task running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        collector.running = False
        log.info("shutdown")

def main():
    load_dotenv()
    configure_logging()
    log.info("service_starting")
    asyncio.run(run())


if __name__ == "__main__":
    main()