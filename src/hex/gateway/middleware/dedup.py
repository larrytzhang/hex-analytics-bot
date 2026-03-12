"""Event deduplication guard.

Provides an in-memory TTL cache keyed by event_id to prevent
processing the same Slack event twice (Slack can deliver duplicates).
"""

import time

from hex.shared.errors import DuplicateEventError


class DeduplicationGuard:
    """In-memory deduplication cache for Slack event IDs.

    Uses a simple dict with timestamps. Events are cached for
    ttl_seconds. Expired entries are lazily cleaned up.

    Attributes:
        _cache:       Dict mapping event_id to timestamp.
        _ttl_seconds: Time-to-live in seconds for cached entries.
    """

    def __init__(self, ttl_seconds: int = 300) -> None:
        """Initialize the deduplication guard.

        Args:
            ttl_seconds: How long to remember event IDs (default 5 minutes).
        """
        self._cache: dict[str, float] = {}
        self._ttl_seconds = ttl_seconds

    def check(self, event_id: str) -> None:
        """Check if an event has already been processed.

        If the event_id is in the cache and not expired, raises
        DuplicateEventError. Otherwise, records the event_id.

        Args:
            event_id: The unique Slack event identifier.

        Raises:
            DuplicateEventError: If the event was already processed.
        """
        now = time.time()

        # Lazy cleanup of expired entries
        self._cleanup(now)

        if event_id in self._cache:
            raise DuplicateEventError(f"Duplicate event: {event_id}")

        self._cache[event_id] = now

    def _cleanup(self, now: float) -> None:
        """Remove expired entries from the cache.

        Args:
            now: Current timestamp for comparison.
        """
        expired = [
            eid for eid, ts in self._cache.items()
            if now - ts > self._ttl_seconds
        ]
        for eid in expired:
            del self._cache[eid]
