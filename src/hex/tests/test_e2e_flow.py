"""End-to-end flow test with real DB, mock LLM, and real Viz.

Simulates: question -> SQL -> execute -> chart -> response.
Verifies SlackResponse has text and image_bytes.
"""

import json
from unittest.mock import AsyncMock

import pytest

from hex.app.orchestrator import AppOrchestrator
from hex.brain.config import BrainConfig
from hex.brain.llm_client import LLMClient
from hex.brain.orchestrator import BrainOrchestrator
from hex.db.engine import SQLiteEngine
from hex.shared.models import ResponseType, SlackRequest
from hex.viz.engine import ChartEngine


def _make_request(text="How many users signed up?"):
    """Create a test SlackRequest."""
    return SlackRequest(
        event_id="Ev1", team_id="T1", channel_id="C1",
        thread_ts="123.456", message_ts="123.456",
        user_id="U1", raw_text=f"<@U999> {text}", clean_text=text,
    )


@pytest.mark.asyncio
async def test_e2e_question_to_chart():
    """Full E2E: question -> Brain (mock LLM) -> real DB -> real Viz -> SlackResponse."""
    # Real DB
    db = SQLiteEngine()

    # Real Viz
    chart_engine = ChartEngine()

    # Mock LLM that returns valid SQL for a bar chart
    config = BrainConfig(model="test", api_key="test", max_sql_retries=2, api_timeout=10)
    llm = LLMClient(config)
    llm.generate = AsyncMock(return_value=json.dumps({
        "sql": "SELECT p.name, COUNT(*) as user_count FROM subscriptions s JOIN plans p ON s.plan_id = p.id GROUP BY p.name",
        "explanation": "Shows number of subscriptions per plan.",
        "suggested_chart": "bar",
        "confidence": 0.95,
    }))

    brain = BrainOrchestrator(config, db, llm)
    mock_slack = AsyncMock()
    orchestrator = AppOrchestrator(brain, chart_engine, mock_slack)

    response = await orchestrator.handle_question(_make_request("Subscriptions per plan"))

    assert response.response_type == ResponseType.TEXT_AND_IMAGE
    assert response.text  # Has text summary
    assert response.image_bytes  # Has chart image
    assert response.image_bytes[:4] == b"\x89PNG"  # Valid PNG
    mock_slack.files_upload_v2.assert_called_once()


@pytest.mark.asyncio
async def test_e2e_text_only_no_chart():
    """E2E: question -> Brain returns NONE chart -> text-only response."""
    db = SQLiteEngine()
    chart_engine = ChartEngine()

    config = BrainConfig(model="test", api_key="test", max_sql_retries=2, api_timeout=10)
    llm = LLMClient(config)
    llm.generate = AsyncMock(return_value=json.dumps({
        "sql": "SELECT COUNT(*) as total FROM users",
        "explanation": "There are 50 users in total.",
        "suggested_chart": "none",
        "confidence": 0.9,
    }))

    brain = BrainOrchestrator(config, db, llm)
    mock_slack = AsyncMock()
    orchestrator = AppOrchestrator(brain, chart_engine, mock_slack)

    response = await orchestrator.handle_question(_make_request("How many users?"))

    assert response.response_type == ResponseType.TEXT
    assert "50" in response.text
