"""Rate limiter for outbound Slack API calls.

Wraps Slack API methods with exponential backoff and jitter
on 429 (Too Many Requests) responses.
"""

import asyncio
import logging
import random
from typing import Any, Callable, Coroutine

from hex.shared.errors import ResponseDeliveryError

logger = logging.getLogger(__name__)


class RateLimiter:
    """Wraps async Slack API calls with 429 retry logic.

    On HTTP 429, applies exponential backoff with jitter, retrying
    up to max_retries times before raising ResponseDeliveryError.

    Attributes:
        _max_retries: Maximum number of retry attempts on 429.
        _base_delay:  Base delay in seconds for exponential backoff.
    """

    def __init__(self, max_retries: int = 3, base_delay: float = 1.0) -> None:
        """Initialize the rate limiter.

        Args:
            max_retries: Maximum retries on 429 responses (default 3).
            base_delay:  Base delay for exponential backoff (default 1.0s).
        """
        self._max_retries = max_retries
        self._base_delay = base_delay

    async def call_with_retry(
        self,
        func: Callable[..., Coroutine[Any, Any, Any]],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute an async Slack API call with 429 retry handling.

        Args:
            func:   The async Slack API method to call.
            *args:  Positional arguments for the API method.
            **kwargs: Keyword arguments for the API method.

        Returns:
            The API response.

        Raises:
            ResponseDeliveryError: If max retries are exhausted.
        """
        last_error = None
        for attempt in range(self._max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "rate_limited" in error_str.lower():
                    last_error = e
                    if attempt < self._max_retries:
                        delay = self._base_delay * (2 ** attempt) + random.uniform(0, 1)
                        logger.warning(
                            "Slack API rate limited (attempt %d/%d), retrying in %.1fs",
                            attempt + 1, self._max_retries + 1, delay,
                        )
                        await asyncio.sleep(delay)
                    continue
                # Non-rate-limit error — don't retry
                raise ResponseDeliveryError(f"Slack API error: {e}") from e

        raise ResponseDeliveryError(
            f"Rate limit retries exhausted after {self._max_retries + 1} attempts: {last_error}"
        )
