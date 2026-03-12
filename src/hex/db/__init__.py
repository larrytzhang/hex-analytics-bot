"""Database execution engine module.

Re-exports the SQLiteEngine implementation for use exclusively by main.py
during dependency wiring. No other module should import directly from db/ —
Brain receives DatabaseEngineInterface via constructor injection.
"""

from hex.db.engine import SQLiteEngine

__all__ = ["SQLiteEngine"]
