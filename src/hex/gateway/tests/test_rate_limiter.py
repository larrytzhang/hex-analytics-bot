"""Tests for the rate limiter.

Verifies that 429 responses trigger backoff and retry,
and max retries are properly enforced.
"""

import pytest

from hex.gateway.middleware.rate_limiter import RateLimiter
from hex.shared.errors import ResponseDeliveryError


class TestRateLimiter:
    """Tests for the RateLimiter."""

    @pytest.mark.asyncio
    async def test_successful_call_returns_immediately(self):
        """A successful call should return without retry."""
        limiter = RateLimiter(max_retries=3)

        async def success_func():
            """Mock successful Slack API call."""
            return {"ok": True}

        result = await limiter.call_with_retry(success_func)
        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_429_triggers_retry_then_succeeds(self):
        """429 error should trigger retry and eventually succeed."""
        limiter = RateLimiter(max_retries=3, base_delay=0.01)
        call_count = 0

        async def flaky_func():
            """Mock function that fails once with 429 then succeeds."""
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("429 rate_limited")
            return {"ok": True}

        result = await limiter.call_with_retry(flaky_func)
        assert result == {"ok": True}
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_max_retries_exhausted_raises_error(self):
        """Exhausting all retries should raise ResponseDeliveryError."""
        limiter = RateLimiter(max_retries=2, base_delay=0.01)

        async def always_429():
            """Mock function that always returns 429."""
            raise Exception("429 rate_limited")

        with pytest.raises(ResponseDeliveryError):
            await limiter.call_with_retry(always_429)

    @pytest.mark.asyncio
    async def test_non_rate_limit_error_raises_immediately(self):
        """Non-429 errors should raise ResponseDeliveryError immediately."""
        limiter = RateLimiter(max_retries=3)

        async def channel_not_found():
            """Mock Slack API channel_not_found error."""
            raise Exception("channel_not_found")

        with pytest.raises(ResponseDeliveryError):
            await limiter.call_with_retry(channel_not_found)
