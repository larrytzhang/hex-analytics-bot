"""SQLite execution engine implementation.

Provides the concrete DatabaseEngineInterface implementation using
an in-memory SQLite database. The default constructor seeds the mock
SaaS analytics schema; passing ``seed=False`` produces a blank engine
that the web layer later populates via :meth:`load_csv` when a user
uploads their own CSV. Either way, the same engine type is returned
so downstream callers (Brain, Viz) see a single interface.
"""

import sqlite3

from hex.shared.errors import (
    ForbiddenQueryError,
    QueryExecutionError,
    QuerySyntaxError,
)
from hex.shared.interfaces import DatabaseEngineInterface
from hex.shared.models import LoadedTable, QueryResult

from hex.db.csv_loader import coerce, parse
from hex.db.sanitizer import validate
from hex.db.schema import create_tables
from hex.db.seed import seed_database


class SQLiteEngine(DatabaseEngineInterface):
    """Concrete implementation of the database execution engine.

    Two construction modes:

    * ``SQLiteEngine()`` — seeds the mock SaaS schema. Used by the Slack
      gateway and by "sample data" web sessions.
    * ``SQLiteEngine(seed=False)`` — blank in-memory DB with only the
      internal ``_meta`` housekeeping table. A user CSV is loaded via
      :meth:`load_csv` before any questions are asked.

    All queries pass through the sanitizer so user-uploaded data still
    enforces read-only access; a malicious question can't turn an
    uploaded table into a write vector.

    Attributes:
        _conn: The SQLite connection instance.
    """

    def __init__(self, *, seed: bool = True) -> None:
        """Initialize the SQLite engine, optionally with mock seed data.

        The ``_meta`` table is always created so :meth:`health_check`
        has a consistent place to probe, regardless of seed path. Keeping
        this in the constructor (rather than in :func:`seed_database`
        alone) means a blank engine still has usable bookkeeping.

        Args:
            seed: If ``True`` (default), apply the mock SaaS schema and
                  seed deterministic demo data. If ``False``, produce a
                  blank DB for CSV upload. Keyword-only so callers are
                  explicit about which mode they want.
        """
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._conn.row_factory = None  # Default tuple rows — matches QueryResult.

        # _meta is infrastructure, not seed data; blank engines still
        # need it so health_check has a table to poll after CSV load.
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS _meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )

        if seed:
            create_tables(self._conn)
            seed_database(self._conn)

    def execute_readonly(self, sql: str) -> QueryResult:
        """Execute a read-only SQL query after sanitization.

        Validates the SQL through the sanitizer, then executes it.
        Translates all sqlite3 errors into shared error types.

        Args:
            sql: The SQL SELECT query to execute.

        Returns:
            QueryResult with success=True and populated data on success,
            or QueryResult with success=False and error message on failure.

        Raises:
            ForbiddenQueryError: If the SQL contains write operations.
            QuerySyntaxError: If the SQL is malformed.
            QueryExecutionError: If a runtime error occurs during execution.
        """
        # Sanitize first — raises ForbiddenQueryError if invalid
        validate(sql)

        try:
            cursor = self._conn.cursor()
            cursor.execute(sql)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()

            return QueryResult(
                success=True,
                columns=columns,
                rows=rows,
                row_count=len(rows),
                query=sql,
            )
        except sqlite3.OperationalError as e:
            error_msg = str(e)
            if "syntax error" in error_msg.lower() or "near" in error_msg.lower():
                raise QuerySyntaxError(error_msg, original_sql=sql) from e
            raise QueryExecutionError(error_msg, original_sql=sql) from e
        except sqlite3.Error as e:
            raise QueryExecutionError(str(e), original_sql=sql) from e

    def get_schema_description(self) -> dict[str, list[dict[str, str]]]:
        """Return the database schema as a dict of table -> column info.

        Introspects sqlite_master for table names and PRAGMA table_info
        for column details. Excludes internal tables (prefixed with _).

        Returns:
            Dict mapping table names to lists of column info dicts,
            each containing 'name' and 'type' keys.
        """
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE '\\_%' ESCAPE '\\' "
            "AND name != 'sqlite_sequence'"
        )
        tables = [row[0] for row in cursor.fetchall()]

        schema: dict[str, list[dict[str, str]]] = {}
        for table in tables:
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [
                {"name": row[1], "type": row[2]}
                for row in cursor.fetchall()
            ]
            schema[table] = columns

        return schema

    def health_check(self) -> bool:
        """Check if the database is alive and has data loaded.

        Executes a simple SELECT 1 query and verifies the _meta table
        has a 'seeded' flag (set by either :func:`seed_database` or
        :meth:`load_csv`). A blank engine returns False until something
        gets loaded, which is the right answer for "is this DB usable."

        Returns:
            True if the database is responsive and has data, False otherwise.
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute("SELECT 1")
            cursor.execute("SELECT value FROM _meta WHERE key = 'seeded'")
            result = cursor.fetchone()
            return result is not None and result[0] == "true"
        except sqlite3.Error:
            return False

    def load_csv(self, csv_bytes: bytes, filename_hint: str) -> LoadedTable:
        """Materialize a user-uploaded CSV into a new table on this engine.

        Only valid on a blank engine (``seed=False``). The engine holds
        at most one uploaded table at a time; calling :meth:`load_csv`
        a second time is not supported and will fail with a DDL
        conflict — that's intentional, sessions are one-CSV-per-session.

        Parsing, sanitization, type inference, and all size/shape limits
        happen in :mod:`hex.db.csv_loader`; this method is the thin
        orchestration layer that turns the parser's output into SQL.

        Args:
            csv_bytes:     Raw CSV file bytes.
            filename_hint: Original filename (used only to derive the
                           table name — the file contents are the
                           source of truth).

        Returns:
            :class:`LoadedTable` with the sanitized table name, inferred
            schema, row count, and up to 5 preview rows for the UI.

        Raises:
            CSVValidationError: If the CSV is malformed, too large,
                empty, or otherwise unusable. Propagated from
                :func:`hex.db.csv_loader.parse` unchanged.
        """
        parsed = parse(csv_bytes, filename_hint)

        # Build the CREATE TABLE DDL. Identifiers are double-quoted so
        # anything that sanitizes to a SQL keyword (e.g. "order") still
        # works. Types come from inference; SQLite is dynamically typed
        # so the types are advisory but still carry through PRAGMA and
        # inform the LLM via get_schema_description().
        col_defs = ", ".join(
            f'"{name}" {dtype}'
            for name, dtype in zip(parsed.column_names, parsed.column_types)
        )
        ddl = f'CREATE TABLE "{parsed.table_name}" ({col_defs})'
        self._conn.execute(ddl)

        # Batched insert. executemany keeps round-trips constant even
        # at MAX_ROWS (10k) so load time is bounded by Python iteration,
        # not SQLite chatter. Coerce each cell to the Python type
        # matching its column — NULL for empty strings so aggregates
        # behave as users expect.
        placeholders = ", ".join("?" for _ in parsed.column_names)
        insert_sql = (
            f'INSERT INTO "{parsed.table_name}" '
            f'({", ".join(f"\"{n}\"" for n in parsed.column_names)}) '
            f"VALUES ({placeholders})"
        )
        coerced_rows = [
            tuple(coerce(cell, t) for cell, t in zip(row, parsed.column_types))
            for row in parsed.rows
        ]
        self._conn.executemany(insert_sql, coerced_rows)

        # Flip the seeded flag so health_check reports True. The web
        # layer uses health_check before trusting a session DB.
        self._conn.execute(
            "INSERT OR REPLACE INTO _meta (key, value) VALUES ('seeded', 'true')"
        )
        self._conn.commit()

        # Preview rows are structured the same way the Brain receives
        # query results downstream (dicts keyed by column). Keeps the
        # web payload uniform with /api/ask responses.
        preview = [
            dict(zip(parsed.column_names, row))
            for row in coerced_rows[:5]
        ]

        columns = [
            {"name": name, "type": dtype}
            for name, dtype in zip(parsed.column_names, parsed.column_types)
        ]

        return LoadedTable(
            table_name=parsed.table_name,
            columns=columns,
            row_count=len(parsed.rows),
            preview_rows=preview,
        )
