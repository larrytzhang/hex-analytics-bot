"""Tests for the Slack event request parser.

Verifies that valid events parse correctly, missing fields are rejected,
and bot mentions are stripped properly.
"""

import pytest

from hex.gateway.core.request_parser import parse
from hex.shared.errors import EventValidationError
from hex.shared.models import SlackRequest


class TestParse:
    """Tests for the parse() function."""

    def _valid_event(self, **overrides) -> dict:
        """Create a valid raw Slack event dict with optional overrides."""
        event = {
            "event_id": "Ev123",
            "team_id": "T123",
            "event": {
                "channel": "C123",
                "text": "<@U999> How many users?",
                "user": "U456",
                "ts": "1234567890.123456",
                "thread_ts": "1234567890.000000",
            },
        }
        event.update(overrides)
        return event

    def test_valid_event_parses_correctly(self):
        """Valid event should produce correct SlackRequest fields."""
        raw = self._valid_event()
        result = parse(raw)

        assert isinstance(result, SlackRequest)
        assert result.event_id == "Ev123"
        assert result.team_id == "T123"
        assert result.channel_id == "C123"
        assert result.user_id == "U456"
        assert result.thread_ts == "1234567890.000000"

    def test_bot_mention_stripped(self):
        """Bot mention should be removed from clean_text."""
        raw = self._valid_event()
        result = parse(raw)

        assert result.clean_text == "How many users?"
        assert "<@U999>" in result.raw_text

    def test_missing_channel_raises_error(self):
        """Missing channel should raise EventValidationError."""
        raw = self._valid_event()
        del raw["event"]["channel"]
        with pytest.raises(EventValidationError):
            parse(raw)

    def test_missing_text_raises_error(self):
        """Missing text should raise EventValidationError."""
        raw = self._valid_event()
        raw["event"]["text"] = ""
        with pytest.raises(EventValidationError):
            parse(raw)

    def test_missing_user_raises_error(self):
        """Missing user should raise EventValidationError."""
        raw = self._valid_event()
        del raw["event"]["user"]
        with pytest.raises(EventValidationError):
            parse(raw)

    def test_thread_ts_defaults_to_message_ts(self):
        """If thread_ts is absent, should fall back to message ts."""
        raw = self._valid_event()
        del raw["event"]["thread_ts"]
        result = parse(raw)
        assert result.thread_ts == "1234567890.123456"

    def test_multiple_bot_mentions_stripped(self):
        """Multiple bot mentions should all be stripped."""
        raw = self._valid_event()
        raw["event"]["text"] = "<@U999> <@U888> show me revenue"
        result = parse(raw)
        assert result.clean_text == "show me revenue"
