import asyncio

from YTComments.Comment import Comment

import json


from kafka import KafkaProducer
#TODO: pass kafka producer instance from outside : collector corrently uses it directly
producer = KafkaProducer(bootstrap_servers='localhost:9092' , value_serializer=lambda v: json.dumps(v).encode('utf-8'))


class CommentsCollector:

    def __init__(self , max_concurrent_tasks = 5):
        self.active_videos = {}#video_id : Comment instance
        self.running = False
        self.semaphore = asyncio.Semaphore(max_concurrent_tasks)

    async def start(self):
        self.running = True
        asyncio.create_task(self._collection_loop())

    async def add_video(self , video_id):

        self.active_videos[video_id] = Comment(video_id)

    async def _collection_loop(self):

        while self.running:
            print("Collection loop running...")
            tasks = []
            for video_id, comment_instance in self.active_videos.items():
                if comment_instance.is_live_streaming():
                    task = asyncio.create_task(self._collect_video_comments(comment_instance))
                    tasks.append(task)
                else:
                    print(f"Video {video_id} is not live streaming anymore.")
                    del self.active_videos[video_id]
            if tasks:
                await asyncio.gather(*tasks , return_exceptions=True)
            await asyncio.sleep(3)


    async def _collect_video_comments(self , comment_instance):

        async with self.semaphore:
            try:
                comments = comment_instance.get_live_chat_messages()
                if comments and 'items' in comments:
                    items = comments['items']
                    print(f"Fetched {len(items)} comments for video {comment_instance.video_id}")
                    #TODO: pass kafta producer instance from outside
                    producer.send( f"comments_{comment_instance.video_id}", value=items)
                    producer.flush() # move to disk from buffer
            except Exception as e:
                print(f"Failed to collect from {comment_instance.video_id}: {e}")
