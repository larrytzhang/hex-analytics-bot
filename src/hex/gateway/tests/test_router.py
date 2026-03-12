"""Tests for the Slack event router.

Uses mocked orchestrator and Slack client to verify the full
handle() flow including timeout handling.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from hex.gateway.core.router import Router
from hex.gateway.core.response_sender import ResponseSender
from hex.gateway.middleware.dedup import DeduplicationGuard
from hex.gateway.middleware.rate_limiter import RateLimiter
from hex.shared.models import ResponseType, SlackResponse


def _make_raw_event(event_id="Ev001"):
    """Create a valid raw Slack event dict."""
    return {
        "event_id": event_id,
        "team_id": "T123",
        "event": {
            "channel": "C123",
            "text": "<@U999> How many users?",
            "user": "U456",
            "ts": "123.456",
        },
    }


@pytest.fixture
def mock_orchestrator():
    """Create a mock OrchestratorInterface."""
    orch = AsyncMock()
    orch.handle_question.return_value = SlackResponse(
        channel_id="C123",
        thread_ts="123.456",
        response_type=ResponseType.TEXT,
        text="There are 42 users.",
    )
    return orch


@pytest.fixture
def mock_slack_client():
    """Create a mock Slack AsyncWebClient."""
    client = AsyncMock()
    return client


@pytest.fixture
def router(mock_orchestrator, mock_slack_client):
    """Create a Router with mocked dependencies."""
    rate_limiter = RateLimiter(max_retries=1)
    sender = ResponseSender(mock_slack_client, rate_limiter)
    dedup = DeduplicationGuard(ttl_seconds=300)
    return Router(
        orchestrator=mock_orchestrator,
        sender=sender,
        dedup=dedup,
        slack_client=mock_slack_client,
        timeout=5,
    )


class TestRouter:
    """Tests for the Router.handle() method."""

    @pytest.mark.asyncio
    async def test_full_handle_flow(self, router, mock_orchestrator, mock_slack_client):
        """Full handle flow should call orchestrator and send response."""
        await router.handle(_make_raw_event())

        mock_orchestrator.handle_question.assert_called_once()
        mock_slack_client.chat_postMessage.assert_called_once()

    @pytest.mark.asyncio
    async def test_thinking_reaction_added_and_removed(self, router, mock_slack_client):
        """Thinking reaction should be added then removed."""
        await router.handle(_make_raw_event())

        mock_slack_client.reactions_add.assert_called_once()
        mock_slack_client.reactions_remove.assert_called_once()

    @pytest.mark.asyncio
    async def test_duplicate_event_silently_ignored(self, router, mock_orchestrator):
        """Duplicate events should be silently ignored."""
        await router.handle(_make_raw_event("Ev_dup"))
        await router.handle(_make_raw_event("Ev_dup"))

        # Orchestrator should only be called once
        assert mock_orchestrator.handle_question.call_count == 1

    @pytest.mark.asyncio
    async def test_timeout_produces_friendly_error(self, mock_slack_client):
        """Timeout should produce a friendly error response."""
        slow_orch = AsyncMock()

        async def slow_handler(*args, **kwargs):
            """Simulate a slow orchestrator."""
            import asyncio
            await asyncio.sleep(10)

        slow_orch.handle_question = slow_handler

        rate_limiter = RateLimiter(max_retries=1)
        sender = ResponseSender(mock_slack_client, rate_limiter)
        dedup = DeduplicationGuard()
        router = Router(slow_orch, sender, dedup, mock_slack_client, timeout=0.1)

        await router.handle(_make_raw_event("Ev_timeout"))

        # Should have sent an error message
        calls = mock_slack_client.chat_postMessage.call_args_list
        assert len(calls) >= 1
        sent_text = calls[-1].kwargs.get("text", "")
        assert "too long" in sent_text.lower() or "try again" in sent_text.lower()
