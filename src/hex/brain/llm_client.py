"""Claude API wrapper for the Brain module.

Handles prompt construction, API calls to the Anthropic SDK, response
parsing, rate limit handling, and timeout management.
"""

import json
import logging
from pathlib import Path

import anthropic

from hex.shared.errors import LLMError, LLMRateLimitError, LLMResponseParseError, LLMTimeoutError
from hex.shared.models import ChartType, GeneratedSQL

from hex.brain.config import BrainConfig

logger = logging.getLogger(__name__)

# Load prompt templates from disk at module level
_TEMPLATE_DIR = Path(__file__).parent / "prompt_templates"


def _load_template(name: str) -> str:
    """Load a prompt template file from the prompt_templates directory.

    Args:
        name: Template filename (e.g. 'system.txt').

    Returns:
        The template content as a string.
    """
    return (_TEMPLATE_DIR / name).read_text()


class LLMClient:
    """Wrapper around the Anthropic SDK for Claude API calls.

    Handles prompt construction from templates, API communication,
    response parsing, and error translation to shared error types.

    Attributes:
        _config: BrainConfig with model and API settings.
        _client: Anthropic async client instance.
    """

    def __init__(self, config: BrainConfig) -> None:
        """Initialize the LLM client with the provided configuration.

        Args:
            config: BrainConfig containing model name, API key, and timeouts.
        """
        self._config = config
        self._client = anthropic.AsyncAnthropic(
            api_key=config.api_key,
            timeout=config.api_timeout,
        )

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Send a prompt to Claude and return the raw response text.

        Args:
            system_prompt: The system-level prompt with role and schema context.
            user_prompt:   The user-level prompt with the question.

        Returns:
            Raw text content from Claude's response.

        Raises:
            LLMRateLimitError: On 429 rate limit response.
            LLMTimeoutError: On request timeout.
            LLMError: On any other API error.
        """
        try:
            response = await self._client.messages.create(
                model=self._config.model,
                max_tokens=self._config.max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return response.content[0].text
        except anthropic.RateLimitError as e:
            logger.warning("Claude API rate limit hit: %s", str(e))
            raise LLMRateLimitError(f"Rate limit exceeded: {e}") from e
        except anthropic.APITimeoutError as e:
            logger.warning("Claude API timeout: %s", str(e))
            raise LLMTimeoutError(f"API request timed out: {e}") from e
        except anthropic.APIError as e:
            logger.error("Claude API error: %s", str(e))
            raise LLMError(f"API error: {e}") from e

    def parse_response(self, raw_response: str) -> GeneratedSQL:
        """Parse the raw LLM response JSON into a GeneratedSQL object.

        Handles JSON extraction, chart type mapping, and validation of
        the response structure.

        Args:
            raw_response: Raw text from Claude's response, expected to be JSON.

        Returns:
            GeneratedSQL with parsed sql, explanation, chart type, and confidence.

        Raises:
            LLMResponseParseError: If the response is not valid JSON or
                missing required fields.
        """
        try:
            # Strip markdown code fences if present
            cleaned = raw_response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()

            data = json.loads(cleaned)

            # Extract and validate fields
            sql = data.get("sql")
            explanation = data.get("explanation", "No explanation provided.")
            confidence = float(data.get("confidence", 0.5))

            # Map chart type string to enum
            chart_str = data.get("suggested_chart", "none")
            try:
                suggested_chart = ChartType(chart_str)
            except ValueError:
                suggested_chart = ChartType.NONE

            return GeneratedSQL(
                sql=sql,
                explanation=explanation,
                suggested_chart=suggested_chart,
                confidence=max(0.0, min(1.0, confidence)),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.error("Failed to parse LLM response: %s", raw_response[:200])
            raise LLMResponseParseError(
                f"Failed to parse LLM response as JSON: {e}"
            ) from e

    def build_system_prompt(self, schema_text: str, glossary_text: str) -> str:
        """Build the system prompt by filling in schema and glossary placeholders.

        Args:
            schema_text:  Formatted schema description string.
            glossary_text: Formatted business glossary string.

        Returns:
            Complete system prompt string ready for the API call.
        """
        template = _load_template("system.txt")
        return template.replace("{schema}", schema_text).replace("{glossary}", glossary_text)

    def build_user_prompt(self, question: str) -> str:
        """Build the user prompt by filling in the question placeholder.

        Args:
            question: The user's plain-English data question.

        Returns:
            Complete user prompt string.
        """
        template = _load_template("user.txt")
        return template.replace("{question}", question)

    def build_correction_prompt(self, question: str, previous_sql: str, error: str) -> str:
        """Build the correction prompt for SQL fix-up retry.

        Args:
            question:     The original user question.
            previous_sql: The SQL that failed execution.
            error:        The error message from the failed execution.

        Returns:
            Complete correction prompt string.
        """
        template = _load_template("correction.txt")
        return (
            template
            .replace("{question}", question)
            .replace("{previous_sql}", previous_sql)
            .replace("{error}", error)
        )
