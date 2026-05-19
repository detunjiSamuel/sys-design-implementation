"""
Tests for SentimentProcessor:
  Priority 1 — analyze_sentiment (pure function, no deps)
  Priority 2 — _classify_sentiment (boundary cases at ±0.05)
  Priority 5 — process_batch (mock MongoDB collection)
"""

import pytest
from unittest.mock import MagicMock, patch
from sparkAnalysis.SentimentProcessor import SentimentProcessor


@pytest.fixture
def processor():
    return SentimentProcessor(
        video_id="test_video",
        spark=MagicMock(),
        mongodb_collection=MagicMock(),
    )


# ---------------------------------------------------------------------------
# Priority 1 — analyze_sentiment
# ---------------------------------------------------------------------------

class TestAnalyzeSentiment:
    def test_returns_required_keys(self, processor):
        result = processor.analyze_sentiment("Great stream!")
        assert set(result.keys()) == {"compound", "classification", "pos", "neg", "neu"}

    def test_positive_text(self, processor):
        result = processor.analyze_sentiment("I love this! Absolutely amazing!")
        assert result["classification"] == "positive"
        assert result["compound"] >= 0.05

    def test_negative_text(self, processor):
        result = processor.analyze_sentiment("This is terrible and completely awful!")
        assert result["classification"] == "negative"
        assert result["compound"] <= -0.05

    def test_neutral_text(self, processor):
        result = processor.analyze_sentiment("The meeting is scheduled for 3pm.")
        assert result["classification"] == "neutral"

    def test_empty_string(self, processor):
        result = processor.analyze_sentiment("")
        assert result["compound"] == 0.0
        assert result["classification"] == "neutral"

    def test_component_scores_sum_to_one(self, processor):
        result = processor.analyze_sentiment("Hello world")
        assert abs(result["pos"] + result["neg"] + result["neu"] - 1.0) < 0.01


# ---------------------------------------------------------------------------
# Priority 2 — _classify_sentiment (boundary cases)
# ---------------------------------------------------------------------------

class TestClassifySentiment:
    @pytest.mark.parametrize("score,expected", [
        (0.05,  "positive"),   # inclusive lower boundary
        (0.5,   "positive"),
        (1.0,   "positive"),
        (-0.05, "negative"),   # inclusive upper boundary
        (-0.5,  "negative"),
        (-1.0,  "negative"),
        (0.049, "neutral"),    # just below positive threshold
        (-0.049, "neutral"),   # just above negative threshold
        (0.0,   "neutral"),
    ])
    def test_boundaries(self, processor, score, expected):
        assert processor._classify_sentiment(score) == expected


# ---------------------------------------------------------------------------
# Priority 5 — process_batch (mock MongoDB)
# ---------------------------------------------------------------------------

class TestProcessBatch:
    def _make_comment(self, text="Hello!", author="Alice"):
        c = MagicMock()
        c.comment = text
        c.author_name = author
        c.profile_image = "http://example.com/img.jpg"
        c.published_at = "2024-01-01T00:00:00Z"
        return c

    def test_empty_batch_is_skipped(self, processor):
        batch_df = MagicMock()
        batch_df.collect.return_value = []

        processor.process_batch(batch_df, batch_id=1)

        processor.collection.insert_many.assert_not_called()

    def test_processes_and_stores_comments(self, processor):
        batch_df = MagicMock()
        batch_df.collect.return_value = [self._make_comment("Great stream!", "Alice")]

        processor.process_batch(batch_df, batch_id=42)

        processor.collection.insert_many.assert_called_once()
        docs = processor.collection.insert_many.call_args[0][0]
        assert len(docs) == 1
        doc = docs[0]
        assert doc["video_id"] == "test_video"
        assert doc["author"] == "Alice"
        assert doc["comment"] == "Great stream!"
        assert doc["batch_id"] == 42
        assert doc["sentiment"]["classification"] in ("positive", "negative", "neutral")

    def test_multiple_comments_all_stored(self, processor):
        batch_df = MagicMock()
        batch_df.collect.return_value = [
            self._make_comment("Love it!", "Alice"),
            self._make_comment("Not great", "Bob"),
        ]

        processor.process_batch(batch_df, batch_id=1)

        docs = processor.collection.insert_many.call_args[0][0]
        assert len(docs) == 2

    def test_mongo_failure_sends_to_dead_letter(self, processor):
        mock_dead_letter = MagicMock()
        processor.dead_letter_producer = mock_dead_letter

        batch_df = MagicMock()
        batch_df.collect.return_value = [self._make_comment()]

        with patch.object(processor, "_insert_many", side_effect=Exception("db down")):
            processor.process_batch(batch_df, batch_id=7)

        mock_dead_letter.send.assert_called_once()
        call_kwargs = mock_dead_letter.send.call_args
        assert call_kwargs[0][0] == "dead_letter_comments"

    def test_mongo_failure_without_dead_letter_does_not_raise(self, processor):
        processor.dead_letter_producer = None
        batch_df = MagicMock()
        batch_df.collect.return_value = [self._make_comment()]

        with patch.object(processor, "_insert_many", side_effect=Exception("db down")):
            processor.process_batch(batch_df, batch_id=8)  # must not raise
