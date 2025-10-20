

import asyncio

from YTComments.CommentCollector import CommentsCollector


# TODOD: make changes to to collector to use asyncio without semaphre:
# reason : they do not really share resors
# TODO : update requests to aihttp reason: there is no reason to block the application while waiting for network response

async def run():
    video_ids = ["JQDaaHJ9u1E"]

    collector = CommentsCollector(max_concurrent_tasks=2)
    for vid in video_ids:
        print("Adding video: " , vid)
        await collector.add_video(vid)
        await asyncio.sleep(3)

    await collector.start()

    try:
        # Keep the main task running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        collector.running = False
        print("\nShutting down gracefully...")

def main():
    print("Hello from etl-live-stream-youtube!")
    asyncio.run(run())


if __name__ == "__main__":
    main()