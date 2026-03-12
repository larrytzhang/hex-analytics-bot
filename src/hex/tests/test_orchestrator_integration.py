"""Integration tests for the AppOrchestrator.

Uses mock Brain, mock Viz, and mock Slack client to verify the
full pipeline: question -> Brain -> Viz -> SlackResponse.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from hex.app.orchestrator import AppOrchestrator
from hex.shared.models import (
    BrainResponse,
    ChartResult,
    ChartType,
    QueryResult,
    ResponseType,
    SlackRequest,
)


def _make_request(text="How many users?"):
    """Create a test SlackRequest."""
    return SlackRequest(
        event_id="Ev1", team_id="T1", channel_id="C1",
        thread_ts="123.456", message_ts="123.456",
        user_id="U1", raw_text=f"<@U999> {text}", clean_text=text,
    )


@pytest.fixture
def mock_brain():
    """Create a mock BrainInterface."""
    brain = AsyncMock()
    brain.ask.return_value = BrainResponse(
        text_summary="There are 42 users.",
        sql_used="SELECT COUNT(*) FROM users",
        query_result=QueryResult(
            success=True, columns=["count"], rows=[(42,)], row_count=1,
            query="SELECT COUNT(*) FROM users",
        ),
        suggested_chart=ChartType.NONE,
    )
    return brain


@pytest.fixture
def mock_chart():
    """Create a mock ChartEngineInterface."""
    chart = MagicMock()
    chart.render.return_value = ChartResult(
        image_bytes=b"\x89PNG_fake", chart_type=ChartType.BAR,
    )
    return chart


@pytest.fixture
def mock_slack():
    """Create a mock Slack AsyncWebClient."""
    return AsyncMock()


class TestAppOrchestrator:
    """Tests for AppOrchestrator.handle_question()."""

    @pytest.mark.asyncio
    async def test_text_only_flow(self, mock_brain, mock_chart, mock_slack):
        """Brain returns NONE chart -> no Viz call, text-only response."""
        orch = AppOrchestrator(mock_brain, mock_chart, mock_slack)
        response = await orch.handle_question(_make_request())

        assert response.response_type == ResponseType.TEXT
        assert "42" in response.text
        mock_chart.render.assert_not_called()

    @pytest.mark.asyncio
    async def test_chart_flow(self, mock_brain, mock_chart, mock_slack):
        """Brain returns BAR chart -> Viz renders -> TEXT_AND_IMAGE response."""
        mock_brain.ask.return_value = BrainResponse(
            text_summary="Revenue by plan",
            sql_used="SELECT ...",
            query_result=QueryResult(
                success=True, columns=["plan", "revenue"],
                rows=[("Starter", 100), ("Pro", 200)], row_count=2,
                query="SELECT ...",
            ),
            suggested_chart=ChartType.BAR,
        )
        orch = AppOrchestrator(mock_brain, mock_chart, mock_slack)
        response = await orch.handle_question(_make_request("Revenue by plan"))

        assert response.response_type == ResponseType.TEXT_AND_IMAGE
        mock_chart.render.assert_called_once()
        mock_slack.files_upload_v2.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_flow(self, mock_chart, mock_slack):
        """Brain raises error -> graceful error response."""
        from hex.shared.errors import BrainError
        brain = AsyncMock()
        brain.ask.side_effect = BrainError("LLM failed")

        orch = AppOrchestrator(brain, mock_chart, mock_slack)
        response = await orch.handle_question(_make_request())

        assert response.response_type == ResponseType.TEXT
        assert "went wrong" in response.text.lower()

    @pytest.mark.asyncio
    async def test_unanswerable_question(self, mock_chart, mock_slack):
        """Brain returns None query_result -> text-only with explanation."""
        brain = AsyncMock()
        brain.ask.return_value = BrainResponse(
            text_summary="I can't answer that.",
            sql_used="", query_result=None,
            suggested_chart=ChartType.NONE,
        )
        orch = AppOrchestrator(brain, mock_chart, mock_slack)
        response = await orch.handle_question(_make_request("What's the weather?"))

        assert "can't answer" in response.text.lower()
        mock_chart.render.assert_not_called()
