"""Tests for :class:`hex.web.session.SessionManager`.

SessionManager owns the web-side isolation contract: each uploaded CSV
gets its own DB + Brain, TTL prunes abandoned sessions, LRU prevents
unbounded memory growth. These tests pin that contract.

We sidestep the real Brain here — the factory receives a lambda returning
a bare mock — so the tests stay fast and don't depend on an LLM client.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from hex.shared.errors import CSVValidationError
from hex.web.session import SessionManager


_CSV_A = b"name,score\nalice,90\nbob,80\n"
_CSV_B = b"city,pop\nnyc,8000000\nla,4000000\n"


def _factory():
    """Return a brain_factory stub that yields a unique MagicMock per call.

    Keeping each brain distinct lets us assert the right one was returned
    by get() later without fuzzy equality checks.
    """
    return lambda _db: MagicMock(name="brain")


def test_create_returns_session_with_unique_id():
    """Each create() mints a fresh UUID — never collides across sessions."""
    sm = SessionManager(_factory())
    a = sm.create(_CSV_A, "a.csv")
    b = sm.create(_CSV_B, "b.csv")
    assert a.session_id != b.session_id
    assert a.loaded_table.table_name == "a"
    assert b.loaded_table.table_name == "b"


def test_get_returns_same_session():
    """get() on an active session returns the same DatasetSession object."""
    sm = SessionManager(_factory())
    s = sm.create(_CSV_A, "a.csv")
    got = sm.get(s.session_id)
    assert got is s


def test_get_unknown_returns_none():
    """Unknown id → None, not exception. UI differentiates with a 404."""
    sm = SessionManager(_factory())
    assert sm.get("does-not-exist") is None


def test_get_refreshes_last_used_at():
    """Touching a session via get() must extend its life (LRU contract)."""
    sm = SessionManager(_factory(), ttl_seconds=60)
    s = sm.create(_CSV_A, "a.csv")
    original = s.last_used_at
    # Sleep a sliver so wall-clock actually advances past float precision.
    time.sleep(0.01)
    sm.get(s.session_id)
    assert s.last_used_at > original


def test_expired_session_is_evicted_on_access():
    """Past-TTL sessions are removed lazily on the next get()/create()."""
    sm = SessionManager(_factory(), ttl_seconds=0)  # Everything is instantly stale.
    s = sm.create(_CSV_A, "a.csv")
    # TTL=0 means the session is already stale by the time we query it.
    time.sleep(0.01)
    assert sm.get(s.session_id) is None
    # The internal map must have dropped the entry, not just returned None.
    assert sm._sessions == {}


def test_lru_eviction_when_at_capacity():
    """Creating past max_sessions pops the least-recently-used entry."""
    sm = SessionManager(_factory(), max_sessions=2)
    a = sm.create(_CSV_A, "a.csv")
    b = sm.create(_CSV_B, "b.csv")
    # Touch a so it's newer than b; b becomes the LRU victim.
    sm.get(a.session_id)
    c = sm.create(_CSV_A, "c.csv")
    assert sm.get(b.session_id) is None
    assert sm.get(a.session_id) is a
    assert sm.get(c.session_id) is c


def test_delete_removes_session():
    """delete() drops the session and returns True; a second delete is False."""
    sm = SessionManager(_factory())
    s = sm.create(_CSV_A, "a.csv")
    assert sm.delete(s.session_id) is True
    assert sm.get(s.session_id) is None
    assert sm.delete(s.session_id) is False


def test_sessions_are_isolated():
    """Two sessions see independent DBs — writes to one don't leak to the other."""
    sm = SessionManager(_factory())
    a = sm.create(_CSV_A, "a.csv")
    b = sm.create(_CSV_B, "b.csv")
    schema_a = a.db.get_schema_description()
    schema_b = b.db.get_schema_description()
    # Each DB has exactly its own table — proof of isolation.
    assert "a" in schema_a and "b" not in schema_a
    assert "b" in schema_b and "a" not in schema_b


def test_create_propagates_csv_validation_error():
    """A malformed CSV surfaces CSVValidationError from the loader unchanged."""
    sm = SessionManager(_factory())
    with pytest.raises(CSVValidationError):
        sm.create(b"", "empty.csv")
