import requests
import os

import structlog

log = structlog.get_logger(__name__)


class Comment:
    def __init__(self , video_id):
        api_key = os.getenv("YT_API_KEY")
        if not api_key:
            raise ValueError("YT_API_KEY environment variable is not set")
        self.api_key = api_key
        self.video_id = video_id
        self.live_chat_id = None
        self.next_page_token = None
        self.is_live = False

        self.get_live_chat_id()

    def _get_live_chat_id_url(self):
        return f'https://www.googleapis.com/youtube/v3/videos?part=liveStreamingDetails&id={self.video_id}&key={self.api_key}'

    def _get_live_chat_messages_url(self):
        return f"https://www.googleapis.com/youtube/v3/liveChat/messages?liveChatId={self.live_chat_id}&part=snippet,authorDetails&key={self.api_key}"


    def get_stream_details(self):
        url = self._get_live_chat_id_url()
        res = requests.get(url , headers={
            "Connection": "close"
        })
        if res.status_code ==  200:
            return res.json()
        else:
            log.error("get_stream_details_error", status_code=res.status_code, response=res.text)
            return None

    def get_live_chat_id(self):
        stream_details = self.get_stream_details()
        if stream_details and 'items' in stream_details and len(stream_details['items']) > 0:
            self.live_chat_id = stream_details['items'][0]['liveStreamingDetails'].get('activeLiveChatId', None)
            if self.live_chat_id:
                self.is_live = True
            return self.live_chat_id
        return None

    def get_live_chat_messages(self):
        url = self._get_live_chat_messages_url()
        if self.next_page_token:
            log.debug("using_next_page_token", token=self.next_page_token)
            url += f"&pageToken={self.next_page_token}"
        res = requests.get(url)
        if res.status_code == 200:
            res =  res.json()
            self.next_page_token =  res.get('nextPageToken', None)
            return res
        else:
            log.error("get_live_chat_messages_error", status_code=res.status_code, response=res.text)
            return None

    def is_live_streaming(self):
        return self.is_live
