"""
Tests for CommentsCollector._collect_video_comments — Priority 4.
The Kafka producer is injected as a mock; no real broker is needed.
asyncio.sleep is patched to keep tests instantaneous.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from YTComments.CommentCollector import CommentsCollector


@pytest.fixture
def mock_producer():
    return MagicMock()


@pytest.fixture
def collector(mock_producer):
    return CommentsCollector(producer=mock_producer)


def _comment_instance(video_id="vid1", items=None):
    inst = MagicMock()
    inst.video_id = video_id
    inst.get_live_chat_messages.return_value = {"items": items} if items is not None else {"items": []}
    return inst


def _yt_item(message="Hello!", author="Alice", image="http://img", published="2024-01-01T00:00:00Z"):
    return {
        "snippet": {"displayMessage": message, "publishedAt": published},
        "authorDetails": {"displayName": author, "profileImageUrl": image},
    }


# ---------------------------------------------------------------------------
# _collect_video_comments
# ---------------------------------------------------------------------------

@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_publishes_comments_to_kafka(mock_sleep, collector, mock_producer):
    inst = _comment_instance(items=[_yt_item("Hello!", "Alice")])

    await collector._collect_video_comments(inst)

    mock_producer.send.assert_called_once_with(
        "comments_vid1",
        value=[{
            "comment": "Hello!",
            "profile_image": "http://img",
            "author_name": "Alice",
            "published_at": "2024-01-01T00:00:00Z",
        }],
    )
    mock_producer.flush.assert_called_once()


@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_multiple_items_all_published(mock_sleep, collector, mock_producer):
    inst = _comment_instance(items=[_yt_item("Hi"), _yt_item("Bye", "Bob")])

    await collector._collect_video_comments(inst)

    payload = mock_producer.send.call_args[1]["value"]
    assert len(payload) == 2


@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_empty_items_skips_publish(mock_sleep, collector, mock_producer):
    inst = _comment_instance(items=[])

    await collector._collect_video_comments(inst)

    mock_producer.send.assert_not_called()


@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_none_response_skips_publish(mock_sleep, collector, mock_producer):
    inst = MagicMock()
    inst.video_id = "vid1"
    inst.get_live_chat_messages.return_value = None

    await collector._collect_video_comments(inst)

    mock_producer.send.assert_not_called()


@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_api_exception_is_caught_and_does_not_propagate(mock_sleep, collector, mock_producer):
    inst = MagicMock()
    inst.video_id = "vid1"
    inst.get_live_chat_messages.side_effect = Exception("network failure")

    await collector._collect_video_comments(inst)  # must not raise

    mock_producer.send.assert_not_called()


@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_kafka_topic_name_includes_video_id(mock_sleep, collector, mock_producer):
    inst = _comment_instance(video_id="abc_123", items=[_yt_item()])

    await collector._collect_video_comments(inst)

    topic = mock_producer.send.call_args[0][0]
    assert topic == "comments_abc_123"
