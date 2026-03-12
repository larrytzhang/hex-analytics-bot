"""Configuration for the Brain (Agentic LLM) module.

Defines BrainConfig with LLM settings including model name, API key,
retry limits, and timeout durations. Reads defaults from environment.
"""

import os
from dataclasses import dataclass


@dataclass
class BrainConfig:
    """Configuration for the Brain module.

    Attributes:
        model:           Claude model ID to use for SQL generation.
        api_key:         Anthropic API key.
        max_sql_retries: Maximum number of SQL correction retries on DB errors.
        api_timeout:     Timeout in seconds for each Claude API call.
        max_tokens:      Maximum tokens for the LLM response.
    """

    model: str = ""
    api_key: str = ""
    max_sql_retries: int = 2
    api_timeout: int = 30
    max_tokens: int = 1024

    def __post_init__(self) -> None:
        """Fill in defaults from environment variables if not provided."""
        if not self.model:
            self.model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
        if not self.api_key:
            self.api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not self.max_sql_retries:
            self.max_sql_retries = int(os.environ.get("MAX_SQL_RETRIES", "2"))
        if not self.api_timeout:
            self.api_timeout = int(os.environ.get("BRAIN_TIMEOUT_SECONDS", "30"))
