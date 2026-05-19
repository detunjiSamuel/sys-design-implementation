import asyncio
import json
import os

import structlog
from kafka import KafkaProducer

from YTComments.Comment import Comment, YouTubeAPIError

log = structlog.get_logger(__name__)


class CommentsCollector:

    def __init__(self, max_concurrent_tasks=5, producer=None):
        self.active_videos = {}  # video_id : Comment instance
        self.running = False
        self.semaphore = asyncio.Semaphore(max_concurrent_tasks)
        self._loop_task = None
        self.producer = producer or KafkaProducer(
            bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            retries=5,
            retry_backoff_ms=300,
            acks='all',
        )

    async def start(self):
        self.running = True
        self._loop_task = asyncio.create_task(self._collection_loop())

    async def add_video(self, video_id):
        try:
            self.active_videos[video_id] = Comment(video_id)
        except YouTubeAPIError as e:
            log.error("add_video_api_error", video_id=video_id, error=str(e))

    async def _collection_loop(self):

        while self.running:
            log.debug("collection_loop_tick")
            tasks = []
            dead_video_ids = []
            for video_id, comment_instance in self.active_videos.items():
                if comment_instance.is_live_streaming():
                    task = asyncio.create_task(self._collect_video_comments(comment_instance))
                    tasks.append(task)
                else:
                    log.info("video_stream_ended", video_id=video_id)
                    dead_video_ids.append(video_id)
            for video_id in dead_video_ids:
                del self.active_videos[video_id]
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, BaseException):
                        log.error(
                            "video_task_failed",
                            error=str(result),
                            exc_type=type(result).__name__,
                        )
            await asyncio.sleep(3)

    async def _collect_video_comments(self, comment_instance):

        async with self.semaphore:
            try:
                comments = comment_instance.get_live_chat_messages()
                if comments and 'items' in comments:
                    items = comments['items']
                    if items:
                        data = [
                            {
                                'comment': i['snippet']['displayMessage'],
                                'profile_image': i['authorDetails']['profileImageUrl'],
                                'author_name': i['authorDetails']['displayName'],
                                'published_at': i['snippet']['publishedAt']

                            } for i in items]

                        log.info(
                            "comments_fetched",
                            video_id=comment_instance.video_id,
                            count=len(items),
                        )
                        self.producer.send(f"comments_{comment_instance.video_id}", value=data)
                        self.producer.flush()

                await asyncio.sleep(2)  # notuced some rate limiting from youtube api

            except Exception as e:
                log.error(
                    "comment_collection_failed",
                    video_id=comment_instance.video_id,
                    error=str(e),
                )
