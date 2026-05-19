"""
Tests for Comment.get_live_chat_id — Priority 3.
All HTTP calls are mocked; no real YouTube API is needed.
"""

import pytest
from unittest.mock import patch, MagicMock
from YTComments.Comment import Comment, YouTubeAPIError


@pytest.fixture
def with_api_key(monkeypatch):
    monkeypatch.setenv("YT_API_KEY", "test_key_123")


def _api_response(live_chat_id=None, status=200):
    mock = MagicMock()
    mock.status_code = status
    mock.text = f"error {status}"
    if status == 200:
        if live_chat_id:
            mock.json.return_value = {
                "items": [
                    {"liveStreamingDetails": {"activeLiveChatId": live_chat_id}}
                ]
            }
        else:
            mock.json.return_value = {"items": []}
    return mock


class TestGetLiveChatId:
    def test_live_stream_sets_chat_id_and_is_live(self, with_api_key):
        with patch("requests.get", return_value=_api_response("chat_abc123")):
            c = Comment("vid1")
        assert c.live_chat_id == "chat_abc123"
        assert c.is_live is True

    def test_no_items_leaves_chat_id_none(self, with_api_key):
        with patch("requests.get", return_value=_api_response()):
            c = Comment("vid1")
        assert c.live_chat_id is None
        assert c.is_live is False

    def test_missing_activeLiveChatId_key_leaves_chat_id_none(self, with_api_key):
        mock = MagicMock()
        mock.status_code = 200
        mock.json.return_value = {"items": [{"liveStreamingDetails": {}}]}
        with patch("requests.get", return_value=mock):
            c = Comment("vid1")
        assert c.live_chat_id is None
        assert c.is_live is False

    def test_missing_api_key_raises_value_error(self, monkeypatch):
        monkeypatch.delenv("YT_API_KEY", raising=False)
        with pytest.raises(ValueError, match="YT_API_KEY"):
            Comment("vid1")

    def test_non_retriable_http_error_raises_youtube_api_error(self, with_api_key):
        with patch("requests.get", return_value=_api_response(status=404)):
            with pytest.raises(YouTubeAPIError) as exc:
                Comment("vid1")
        assert exc.value.status_code == 404

    def test_is_live_streaming_reflects_live_state(self, with_api_key):
        with patch("requests.get", return_value=_api_response("chat_xyz")):
            c = Comment("vid1")
        assert c.is_live_streaming() is True

    def test_is_live_streaming_false_when_not_live(self, with_api_key):
        with patch("requests.get", return_value=_api_response()):
            c = Comment("vid1")
        assert c.is_live_streaming() is False
