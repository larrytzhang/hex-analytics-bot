"""Web module configuration.

Loaded from environment variables via pydantic-settings. Defaults are
chosen so the app boots locally with no env config (HOST=0.0.0.0 so
container deploys also work out of the box).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class WebConfig(BaseSettings):
    """Settings for the FastAPI web demo.

    Attributes:
        HOST:                Bind address. 0.0.0.0 lets containers/Render reach it.
        PORT:                TCP port. Render injects $PORT, so we read it here.
        REQUEST_TIMEOUT_SECONDS: Hard ceiling on /api/ask. The brain pipeline
                             can take 5–10s; 30 leaves comfortable headroom but
                             still bounds runaway calls.
        MAX_QUESTION_LENGTH: Reject obviously oversized inputs early to keep
                             token cost predictable for an unauthenticated demo.
    """

    HOST: str = "0.0.0.0"
    PORT: int = 8000
    REQUEST_TIMEOUT_SECONDS: int = 30
    MAX_QUESTION_LENGTH: int = 500
    # Upload guards. MAX_UPLOAD_BYTES is a second line of defense; the
    # CSV loader enforces its own 5MB cap. Overlapping is intentional.
    MAX_UPLOAD_BYTES: int = 5 * 1024 * 1024
    SESSION_TTL_SECONDS: int = 1800
    MAX_SESSIONS: int = 20

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
