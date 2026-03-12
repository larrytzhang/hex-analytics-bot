"""Configuration for the Slack Gateway module.

Uses Pydantic BaseSettings to load configuration from environment
variables with sensible defaults.
"""

from pydantic_settings import BaseSettings


class GatewayConfig(BaseSettings):
    """Gateway configuration loaded from environment variables.

    Attributes:
        SLACK_BOT_TOKEN:         Bot OAuth token (xoxb-...).
        SLACK_APP_TOKEN:         App token for Socket Mode (xapp-...).
        BRAIN_TIMEOUT_SECONDS:   Max time to wait for Brain response.
        DEDUP_TTL_SECONDS:       TTL for the event deduplication cache.
        RATE_LIMIT_MAX_RETRIES:  Max retries on Slack API 429 responses.
        LOG_LEVEL:               Logging verbosity level.
    """

    SLACK_BOT_TOKEN: str = ""
    SLACK_APP_TOKEN: str = ""
    BRAIN_TIMEOUT_SECONDS: int = 30
    DEDUP_TTL_SECONDS: int = 300
    RATE_LIMIT_MAX_RETRIES: int = 3
    LOG_LEVEL: str = "INFO"

    model_config = {"env_file": ".env", "extra": "ignore"}
