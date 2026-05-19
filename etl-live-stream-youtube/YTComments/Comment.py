import os

import requests
import structlog
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

log = structlog.get_logger(__name__)

_RETRIABLE_STATUSES = {429, 500, 502, 503, 504}


class YouTubeAPIError(Exception):
    def __init__(self, status_code: int, body: str = ""):
        super().__init__(f"status={status_code} body={body}")
        self.status_code = status_code


def _is_retriable(exc: Exception) -> bool:
    return isinstance(exc, YouTubeAPIError) and exc.status_code in _RETRIABLE_STATUSES


def _log_retry(retry_state) -> None:
    log.warning(
        "youtube_api_retry",
        attempt=retry_state.attempt_number,
        exception=str(retry_state.outcome.exception()),
    )


class Comment:
    def __init__(self, video_id):
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

    @retry(
        retry=retry_if_exception(_is_retriable),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(5),
        before_sleep=_log_retry,
    )
    def get_stream_details(self):
        url = self._get_live_chat_id_url()
        res = requests.get(url, headers={"Connection": "close"})
        if res.status_code == 200:
            return res.json()
        raise YouTubeAPIError(res.status_code, res.text)

    def get_live_chat_id(self):
        stream_details = self.get_stream_details()
        if 'items' in stream_details and len(stream_details['items']) > 0:
            self.live_chat_id = stream_details['items'][0]['liveStreamingDetails'].get('activeLiveChatId')
            if self.live_chat_id:
                self.is_live = True
        return self.live_chat_id

    @retry(
        retry=retry_if_exception(_is_retriable),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(5),
        before_sleep=_log_retry,
    )
    def get_live_chat_messages(self):
        url = self._get_live_chat_messages_url()
        if self.next_page_token:
            log.debug("using_next_page_token", token=self.next_page_token)
            url += f"&pageToken={self.next_page_token}"
        res = requests.get(url)
        if res.status_code == 200:
            data = res.json()
            self.next_page_token = data.get('nextPageToken', None)
            return data
        raise YouTubeAPIError(res.status_code, res.text)

    def is_live_streaming(self):
        return self.is_live
