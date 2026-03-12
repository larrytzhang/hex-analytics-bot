"""Tests for the deduplication guard.

Verifies that duplicate events are caught, new events pass through,
and TTL expiry allows re-processing.
"""

import time
from unittest.mock import patch

import pytest

from hex.gateway.middleware.dedup import DeduplicationGuard
from hex.shared.errors import DuplicateEventError


class TestDeduplicationGuard:
    """Tests for the DeduplicationGuard."""

    def test_new_event_passes(self):
        """A new event_id should pass through without error."""
        guard = DeduplicationGuard(ttl_seconds=300)
        guard.check("event_1")  # Should not raise

    def test_duplicate_event_raises_error(self):
        """A duplicate event_id should raise DuplicateEventError."""
        guard = DeduplicationGuard(ttl_seconds=300)
        guard.check("event_1")

        with pytest.raises(DuplicateEventError):
            guard.check("event_1")

    def test_different_events_both_pass(self):
        """Different event IDs should both pass through."""
        guard = DeduplicationGuard(ttl_seconds=300)
        guard.check("event_1")
        guard.check("event_2")  # Should not raise

    def test_ttl_expiry_allows_reprocessing(self):
        """After TTL expires, the same event_id should be allowed again."""
        guard = DeduplicationGuard(ttl_seconds=1)
        guard.check("event_1")

        # Simulate time passing
        with patch("hex.gateway.middleware.dedup.time") as mock_time:
            # First check at time 0
            mock_time.time.return_value = time.time() + 2
            # After TTL expiry, should pass
            guard.check("event_1")  # Should not raise
