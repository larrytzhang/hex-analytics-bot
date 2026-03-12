"""Tests for the LLM client.

Uses mocked Anthropic API to verify prompt construction,
API call handling, and JSON response parsing into GeneratedSQL.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hex.brain.config import BrainConfig
from hex.brain.llm_client import LLMClient
from hex.shared.errors import LLMResponseParseError
from hex.shared.models import ChartType


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
def client(config):
    """Create an LLMClient with test config."""
    return LLMClient(config)


class TestParseResponse:
    """Tests for JSON response parsing."""

    def test_valid_json_parses_correctly(self, client):
        """Valid JSON response should parse into GeneratedSQL."""
        raw = json.dumps({
            "sql": "SELECT COUNT(*) FROM users",
            "explanation": "Counts all users.",
            "suggested_chart": "none",
            "confidence": 0.9,
        })
        result = client.parse_response(raw)
        assert result.sql == "SELECT COUNT(*) FROM users"
        assert result.explanation == "Counts all users."
        assert result.suggested_chart == ChartType.NONE
        assert result.confidence == 0.9

    def test_null_sql_parses_correctly(self, client):
        """Null SQL (unanswerable question) should parse with sql=None."""
        raw = json.dumps({
            "sql": None,
            "explanation": "Can't answer that.",
            "suggested_chart": "none",
            "confidence": 0.0,
        })
        result = client.parse_response(raw)
        assert result.sql is None
        assert result.confidence == 0.0

    def test_invalid_json_raises_parse_error(self, client):
        """Non-JSON response should raise LLMResponseParseError."""
        with pytest.raises(LLMResponseParseError):
            client.parse_response("This is not JSON")

    def test_markdown_fenced_json_parsed(self, client):
        """JSON wrapped in markdown code fences should still parse."""
        raw = '```json\n{"sql": "SELECT 1", "explanation": "test", "suggested_chart": "bar", "confidence": 0.8}\n```'
        result = client.parse_response(raw)
        assert result.sql == "SELECT 1"
        assert result.suggested_chart == ChartType.BAR

    def test_unknown_chart_type_defaults_to_none(self, client):
        """Unknown chart type string should default to ChartType.NONE."""
        raw = json.dumps({
            "sql": "SELECT 1",
            "explanation": "test",
            "suggested_chart": "unknown_type",
            "confidence": 0.5,
        })
        result = client.parse_response(raw)
        assert result.suggested_chart == ChartType.NONE

    def test_confidence_clamped_to_range(self, client):
        """Confidence values should be clamped to 0.0-1.0."""
        raw = json.dumps({
            "sql": "SELECT 1",
            "explanation": "test",
            "suggested_chart": "none",
            "confidence": 1.5,
        })
        result = client.parse_response(raw)
        assert result.confidence == 1.0


class TestPromptBuilding:
    """Tests for prompt template construction."""

    def test_system_prompt_includes_schema(self, client):
        """System prompt should include the schema text."""
        prompt = client.build_system_prompt("SCHEMA_TEXT_HERE", "GLOSSARY_HERE")
        assert "SCHEMA_TEXT_HERE" in prompt
        assert "GLOSSARY_HERE" in prompt

    def test_user_prompt_includes_question(self, client):
        """User prompt should include the question text."""
        prompt = client.build_user_prompt("How many users?")
        assert "How many users?" in prompt

    def test_correction_prompt_includes_all_fields(self, client):
        """Correction prompt should include question, SQL, and error."""
        prompt = client.build_correction_prompt(
            "How many users?", "SELECT COUNT(*) FROM userz", "no such table: userz"
        )
        assert "How many users?" in prompt
        assert "SELECT COUNT(*) FROM userz" in prompt
        assert "no such table: userz" in prompt
