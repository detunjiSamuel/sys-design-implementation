

import asyncio

from YTComments.CommentCollector import CommentsCollector




async def run():
    video_ids = ["lLTEkaB8l1A" , "_MXcIddl6eA" , "wkyXiX5Fc6E"]

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