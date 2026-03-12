"""Tests for the Brain orchestrator.

Uses mock LLM and mock DB to verify the full pipeline flows correctly,
and that BrainResponse has the expected structure.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hex.brain.config import BrainConfig
from hex.brain.llm_client import LLMClient
from hex.brain.orchestrator import BrainOrchestrator
from hex.shared.models import BrainResponse, ChartType, QueryResult


@pytest.fixture
def mock_db():
    """Create a mock DatabaseEngineInterface."""
    db = MagicMock()
    db.get_schema_description.return_value = {
        "users": [
            {"name": "id", "type": "INTEGER"},
            {"name": "name", "type": "TEXT"},
        ],
    }
    db.execute_readonly.return_value = QueryResult(
        success=True,
        columns=["count"],
        rows=[(42,)],
        row_count=1,
        query="SELECT COUNT(*) FROM users",
    )
    return db


@pytest.fixture
def config():
    """Create a test BrainConfig."""
    return BrainConfig(
        model="claude-test",
        api_key="test-key",
        max_sql_retries=2,
        api_timeout=10,
    )


@pytest.fixture
def mock_llm_client(config):
    """Create an LLMClient with mocked generate method."""
    client = LLMClient(config)
    client.generate = AsyncMock(return_value=json.dumps({
        "sql": "SELECT COUNT(*) FROM users",
        "explanation": "Counts all users in the database.",
        "suggested_chart": "none",
        "confidence": 0.95,
    }))
    return client


@pytest.fixture
def orchestrator(config, mock_db, mock_llm_client):
    """Create a BrainOrchestrator with mocked dependencies."""
    return BrainOrchestrator(config, mock_db, mock_llm_client)


class TestBrainOrchestrator:
    """Tests for the BrainOrchestrator.ask() method."""

    @pytest.mark.asyncio
    async def test_question_flows_through_pipeline(self, orchestrator):
        """A valid question should flow through the full pipeline."""
        response = await orchestrator.ask("How many users are there?")
        assert isinstance(response, BrainResponse)
        assert response.text_summary is not None
        assert response.query_result is not None
        assert response.query_result.success is True

    @pytest.mark.asyncio
    async def test_brain_response_structure(self, orchestrator):
        """BrainResponse should have all expected fields."""
        response = await orchestrator.ask("How many users?")
        assert hasattr(response, "text_summary")
        assert hasattr(response, "sql_used")
        assert hasattr(response, "query_result")
        assert hasattr(response, "suggested_chart")
        assert hasattr(response, "error")
        assert hasattr(response, "retries_used")

    @pytest.mark.asyncio
    async def test_unanswerable_question(self, config, mock_db):
        """Unanswerable question (sql=None) should return text explanation."""
        client = LLMClient(config)
        client.generate = AsyncMock(return_value=json.dumps({
            "sql": None,
            "explanation": "Cannot answer that.",
            "suggested_chart": "none",
            "confidence": 0.0,
        }))
        orch = BrainOrchestrator(config, mock_db, client)
        response = await orch.ask("What's the weather?")
        assert response.query_result is None
        assert response.suggested_chart == ChartType.NONE
        assert "Cannot answer" in response.text_summary

    @pytest.mark.asyncio
    async def test_low_confidence_adds_warning(self, config, mock_db):
        """Low confidence (<0.5) should prepend warning to text_summary."""
        client = LLMClient(config)
        client.generate = AsyncMock(return_value=json.dumps({
            "sql": "SELECT COUNT(*) FROM users",
            "explanation": "Maybe this works.",
            "suggested_chart": "none",
            "confidence": 0.3,
        }))
        orch = BrainOrchestrator(config, mock_db, client)
        response = await orch.ask("Some unclear question")
        assert "Low confidence" in response.text_summary
