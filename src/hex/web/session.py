"""Per-browser session store for user-uploaded CSVs.

Each upload spawns a fresh :class:`SQLiteEngine` + :class:`BrainInterface`
bound to it, keyed by a server-minted UUID. The frontend echoes the
UUID on every ``/api/ask`` so questions route to the right dataset.

Isolation is load-bearing for a public demo URL: two reviewers clicking
through at the same time must not see each other's data. We use an
in-memory OrderedDict (cheap LRU) with TTL + concurrent-session caps
instead of anything persistent — the Render free tier's disk is
ephemeral anyway, and a lost session after server restart is fine.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable

from hex.db.engine import SQLiteEngine
from hex.shared.interfaces import BrainInterface
from hex.shared.models import LoadedTable


# Factory signature: given a DB engine, return a Brain wired to it.
# Inverted so SessionManager has no import dependency on brain/.
BrainFactory = Callable[[SQLiteEngine], BrainInterface]


@dataclass
class DatasetSession:
    """One user's uploaded-dataset session.

    Attributes:
        session_id:    Server-minted UUID returned to the client.
        db:            Blank SQLiteEngine with the uploaded CSV loaded.
        brain:         Brain wired to this session's DB (glossary off).
        loaded_table:  Table metadata for /api/session restore requests.
        created_at:    Wall-clock epoch seconds at creation.
        last_used_at:  Touched on every get(); drives LRU + TTL eviction.
    """

    session_id: str
    db: SQLiteEngine
    brain: BrainInterface
    loaded_table: LoadedTable
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)


class SessionManager:
    """Thread-safe in-memory registry of dataset sessions.

    Concurrency: FastAPI may dispatch multiple requests against the
    manager at once (upload + ask on different sessions); a single
    lock around the OrderedDict is plenty here — operations are O(1)
    and nothing blocks inside the critical section.

    Eviction:
      * TTL — sessions untouched for ``ttl_seconds`` are purged on the
        next get() or create(). Lazy to keep memory overhead zero.
      * LRU cap — when creating would push us past ``max_sessions``, the
        least-recently-used session is dropped.
    """

    def __init__(
        self,
        brain_factory: BrainFactory,
        *,
        max_sessions: int = 20,
        ttl_seconds: int = 1800,
    ) -> None:
        """Initialize an empty manager.

        Args:
            brain_factory: Callable that wires a Brain to a given engine.
                Passed in so the manager doesn't import brain internals.
            max_sessions: Hard cap on concurrent sessions — bounds worst
                case memory (each session holds ~5MB uploaded data plus
                Brain/LLM client overhead).
            ttl_seconds: Idle lifetime before lazy eviction. 30min by
                default matches typical reviewer attention span.
        """
        self._brain_factory = brain_factory
        self._max = max_sessions
        self._ttl = ttl_seconds
        self._sessions: OrderedDict[str, DatasetSession] = OrderedDict()
        self._lock = threading.Lock()

    def create(self, csv_bytes: bytes, filename_hint: str) -> DatasetSession:
        """Parse a CSV, build a session for it, and register it.

        The heavy work (CSV parse, DDL, inserts) runs inside the lock
        only after we've claimed a slot — if eviction needs to run
        first, it does, and we never have two sessions racing for the
        same slot.

        Args:
            csv_bytes:     Raw CSV bytes from the upload endpoint.
            filename_hint: Original filename; used to derive the table
                           name via :func:`csv_loader.parse`.

        Returns:
            A fresh :class:`DatasetSession`.

        Raises:
            CSVValidationError: If parsing/validation fails. Propagated.
        """
        db = SQLiteEngine(seed=False)
        loaded = db.load_csv(csv_bytes, filename_hint)
        brain = self._brain_factory(db)
        session = DatasetSession(
            session_id=uuid.uuid4().hex,
            db=db,
            brain=brain,
            loaded_table=loaded,
        )
        with self._lock:
            self._evict_expired_locked()
            while len(self._sessions) >= self._max:
                # popitem(last=False) pops the LRU — matches our
                # touch-on-get pattern where get() moves to the end.
                self._sessions.popitem(last=False)
            self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> DatasetSession | None:
        """Look up and refresh a session, or return None if gone/expired.

        Touching ``last_used_at`` + moving to the end of the OrderedDict
        implements the LRU contract: active sessions never get evicted,
        idle ones drift to the front and die first.
        """
        now = time.time()
        with self._lock:
            self._evict_expired_locked()
            session = self._sessions.get(session_id)
            if session is None:
                return None
            session.last_used_at = now
            self._sessions.move_to_end(session_id)
            return session

    def delete(self, session_id: str) -> bool:
        """Explicitly drop a session. Returns True if one was removed."""
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def _evict_expired_locked(self) -> None:
        """Remove every session past its TTL. Caller must hold ``_lock``.

        OrderedDict preserves insertion/refresh order, so we only need
        to scan from the front until we hit a live session — all
        remaining ones are newer.
        """
        now = time.time()
        stale: list[str] = []
        for sid, session in self._sessions.items():
            if now - session.last_used_at > self._ttl:
                stale.append(sid)
            else:
                break
        for sid in stale:
            self._sessions.pop(sid, None)
