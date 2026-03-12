"""SQLite execution engine implementation.

Provides the concrete DatabaseEngineInterface implementation using
an in-memory SQLite database. Automatically creates tables and seeds
data on initialization.
"""

import sqlite3

from hex.shared.errors import (
    ForbiddenQueryError,
    QueryExecutionError,
    QuerySyntaxError,
)
from hex.shared.interfaces import DatabaseEngineInterface
from hex.shared.models import QueryResult

from hex.db.sanitizer import validate
from hex.db.schema import create_tables
from hex.db.seed import seed_database


class SQLiteEngine(DatabaseEngineInterface):
    """Concrete implementation of the database execution engine.

    Uses an in-memory SQLite database that is automatically initialized
    with schema and seed data on construction. All queries are validated
    through the sanitizer before execution to enforce read-only access.

    Attributes:
        _conn: The SQLite connection instance.
    """

    def __init__(self) -> None:
        """Initialize the SQLite engine with schema and seed data.

        Creates an in-memory SQLite database, applies the schema DDL,
        and populates it with deterministic seed data.
        """
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._conn.row_factory = None  # Use default tuple rows
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
        """Check if the database is alive and seeded.

        Executes a simple SELECT 1 query and verifies the _meta table
        has a 'seeded' flag.

        Returns:
            True if the database is responsive and seeded, False otherwise.
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute("SELECT 1")
            cursor.execute("SELECT value FROM _meta WHERE key = 'seeded'")
            result = cursor.fetchone()
            return result is not None and result[0] == "true"
        except sqlite3.Error:
            return False
