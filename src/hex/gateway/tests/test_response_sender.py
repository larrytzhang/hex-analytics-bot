"""Tests for the response sender.

Verifies that TEXT responses call chat_postMessage correctly,
TEXT_AND_IMAGE responses send text in-thread, and Slack API
errors raise ResponseDeliveryError.
"""

from unittest.mock import AsyncMock

import pytest

from hex.gateway.core.response_sender import ResponseSender
from hex.gateway.middleware.rate_limiter import RateLimiter
from hex.shared.errors import ResponseDeliveryError
from hex.shared.models import ResponseType, SlackResponse


@pytest.fixture
def mock_client():
    """Create a mock Slack AsyncWebClient."""
    return AsyncMock()


@pytest.fixture
def sender(mock_client):
    """Create a ResponseSender with mocked Slack client."""
    rate_limiter = RateLimiter(max_retries=1, base_delay=0.01)
    return ResponseSender(mock_client, rate_limiter)


class TestResponseSender:
    """Tests for the ResponseSender.send() method."""

    @pytest.mark.asyncio
    async def test_text_response_calls_chat_post_message(self, sender, mock_client):
        """TEXT response should call chat_postMessage with correct args."""
        response = SlackResponse(
            channel_id="C123",
            thread_ts="123.456",
            response_type=ResponseType.TEXT,
            text="Hello world",
        )

        await sender.send(response)

        mock_client.chat_postMessage.assert_called_once_with(
            channel="C123",
            thread_ts="123.456",
            text="Hello world",
        )

    @pytest.mark.asyncio
    async def test_text_and_image_response_sends_text(self, sender, mock_client):
        """TEXT_AND_IMAGE response should send text in-thread."""
        response = SlackResponse(
            channel_id="C123",
            thread_ts="123.456",
            response_type=ResponseType.TEXT_AND_IMAGE,
            text="Here's the chart",
            image_bytes=b"fake_png",
        )

        await sender.send(response)

        mock_client.chat_postMessage.assert_called_once_with(
            channel="C123",
            thread_ts="123.456",
            text="Here's the chart",
        )

    @pytest.mark.asyncio
    async def test_slack_api_error_raises_delivery_error(self, mock_client):
        """Slack API error should raise ResponseDeliveryError."""
        mock_client.chat_postMessage.side_effect = Exception("channel_not_found")
        rate_limiter = RateLimiter(max_retries=0, base_delay=0.01)
        sender = ResponseSender(mock_client, rate_limiter)

        response = SlackResponse(
            channel_id="C_invalid",
            thread_ts="123.456",
            response_type=ResponseType.TEXT,
            text="test",
        )

        with pytest.raises(ResponseDeliveryError):
            await sender.send(response)
