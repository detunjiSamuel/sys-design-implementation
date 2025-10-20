import requests
import os

#TODO: pass API_KEY in data class from env variable

API_KEY =os.getenv("YT_API_KEY")


class Comment:
    def __init__(self , video_id):
        self.video_id = video_id
        self.live_chat_id = None
        self.next_page_token = None
        self.is_live = False

        self.get_live_chat_id()

    def _get_live_chat_id_url(self):
        return f'https://www.googleapis.com/youtube/v3/videos?part=liveStreamingDetails&id={self.video_id}&key={API_KEY}'

    def _get_live_chat_messages_url(self):
        return f"https://www.googleapis.com/youtube/v3/liveChat/messages?liveChatId={self.live_chat_id}&part=snippet,authorDetails&key={API_KEY}"


    def get_stream_details(self):
        url = self._get_live_chat_id_url()
        res = requests.get(url , headers={
            "Connection": "close"
        })
        if res.status_code ==  200:
            return res.json()
        else:
            print(f"Error_getStreamDetails: {res.status_code} - {res.text}")
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
            print(f"Using next page token: {self.next_page_token}")
            url += f"&pageToken={self.next_page_token}"
        res = requests.get(url)
        if res.status_code == 200:
            res =  res.json()
            self.next_page_token =  res.get('nextPageToken', None)
            return res
        else:
            print(f"Error_getLiveChatMessage: {res.status_code} - {res.text}")
            return None

    def is_live_streaming(self):
        return self.is_live
