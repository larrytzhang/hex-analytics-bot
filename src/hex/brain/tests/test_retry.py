"""Tests for the retry handler.

Verifies that DB errors trigger correction re-prompts,
WriteOperationDetected fails immediately, and max retries
are respected.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from hex.brain.config import BrainConfig
from hex.brain.llm_client import LLMClient
from hex.brain.retry import RetryHandler
from hex.shared.errors import QueryExecutionError, SQLGenerationError, WriteOperationDetected
from hex.shared.models import ChartType, GeneratedSQL, QueryResult


@pytest.fixture
def mock_db():
    """Create a mock DatabaseEngineInterface."""
    return MagicMock()


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
def mock_llm(config):
    """Create an LLMClient with mocked generate method."""
    client = LLMClient(config)
    client.generate = AsyncMock(return_value=json.dumps({
        "sql": "SELECT COUNT(*) FROM users",
        "explanation": "Fixed query.",
        "suggested_chart": "none",
        "confidence": 0.9,
    }))
    return client


class TestRetryHandler:
    """Tests for the RetryHandler.execute_with_retries() method."""

    @pytest.mark.asyncio
    async def test_successful_execution_no_retries(self, mock_db, mock_llm):
        """Successful execution should return result with 0 retries."""
        mock_db.execute_readonly.return_value = QueryResult(
            success=True, columns=["cnt"], rows=[(42,)], row_count=1,
            query="SELECT COUNT(*) FROM users",
        )
        handler = RetryHandler(mock_db, mock_llm, max_retries=2)
        generated = GeneratedSQL(
            sql="SELECT COUNT(*) FROM users",
            explanation="Count users",
            suggested_chart=ChartType.NONE,
            confidence=0.9,
        )

        result, retries = await handler.execute_with_retries(
            generated, "How many users?", "system prompt"
        )
        assert result.success is True
        assert retries == 0

    @pytest.mark.asyncio
    async def test_db_error_triggers_correction(self, mock_db, mock_llm):
        """DB error should trigger LLM correction and retry."""
        # First call fails, second succeeds
        mock_db.execute_readonly.side_effect = [
            QueryExecutionError("no such column: foo"),
            QueryResult(
                success=True, columns=["cnt"], rows=[(42,)], row_count=1,
                query="SELECT COUNT(*) FROM users",
            ),
        ]
        handler = RetryHandler(mock_db, mock_llm, max_retries=2)
        generated = GeneratedSQL(
            sql="SELECT foo FROM users",
            explanation="Query",
            suggested_chart=ChartType.NONE,
            confidence=0.9,
        )

        result, retries = await handler.execute_with_retries(
            generated, "How many users?", "system prompt"
        )
        assert result.success is True
        assert retries == 1

    @pytest.mark.asyncio
    async def test_write_operation_fails_immediately(self, mock_db, mock_llm):
        """WriteOperationDetected should fail immediately without retry."""
        handler = RetryHandler(mock_db, mock_llm, max_retries=2)
        generated = GeneratedSQL(
            sql="DROP TABLE users",
            explanation="Drop it",
            suggested_chart=ChartType.NONE,
            confidence=0.9,
        )

        with pytest.raises(WriteOperationDetected):
            await handler.execute_with_retries(
                generated, "Drop users", "system prompt"
            )

    @pytest.mark.asyncio
    async def test_max_retries_exhausted_raises_error(self, mock_db, mock_llm):
        """Exhausting all retries should raise SQLGenerationError."""
        mock_db.execute_readonly.side_effect = QueryExecutionError("always fails")
        handler = RetryHandler(mock_db, mock_llm, max_retries=2)
        generated = GeneratedSQL(
            sql="SELECT bad FROM users",
            explanation="Query",
            suggested_chart=ChartType.NONE,
            confidence=0.9,
        )

        with pytest.raises(SQLGenerationError):
            await handler.execute_with_retries(
                generated, "question", "system prompt"
            )
