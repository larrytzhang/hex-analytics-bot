"""Tests for the SQL sanitizer.

Verifies that forbidden operations are blocked and valid
SELECT queries pass through successfully.
"""

import pytest

from hex.db.sanitizer import validate
from hex.shared.errors import ForbiddenQueryError


class TestForbiddenOperations:
    """Tests that write/DDL operations are properly blocked."""

    @pytest.mark.parametrize("sql", [
        "DROP TABLE users",
        "ALTER TABLE users ADD COLUMN x TEXT",
        "INSERT INTO users (email, name) VALUES ('a', 'b')",
        "UPDATE users SET name = 'x' WHERE id = 1",
        "DELETE FROM users WHERE id = 1",
        "ATTACH DATABASE ':memory:' AS other",
        "DETACH DATABASE other",
        "PRAGMA table_info(users)",
        "CREATE TABLE evil (id INTEGER)",
        "VACUUM",
        "REINDEX",
    ])
    def test_forbidden_keywords_blocked(self, sql):
        """Forbidden SQL keywords should raise ForbiddenQueryError."""
        with pytest.raises(ForbiddenQueryError):
            validate(sql)

    def test_case_insensitive_blocking(self):
        """Forbidden keywords should be caught regardless of case."""
        with pytest.raises(ForbiddenQueryError):
            validate("drop TABLE users")
        with pytest.raises(ForbiddenQueryError):
            validate("Insert into users VALUES ('a')")


class TestMultiStatement:
    """Tests that multiple SQL statements are blocked."""

    def test_multi_statement_blocked(self):
        """Multiple statements separated by semicolons should be rejected."""
        with pytest.raises(ForbiddenQueryError):
            validate("SELECT 1; SELECT 2")

    def test_trailing_semicolon_allowed(self):
        """A trailing semicolon on a single statement should be allowed."""
        validate("SELECT * FROM users;")  # Should not raise


class TestCommentInjection:
    """Tests that SQL comment injection attempts are blocked."""

    def test_double_dash_comment_blocked(self):
        """Double-dash comments should be rejected."""
        with pytest.raises(ForbiddenQueryError):
            validate("SELECT * FROM users -- this is a comment")

    def test_block_comment_blocked(self):
        """Block comments (/* */) should be rejected."""
        with pytest.raises(ForbiddenQueryError):
            validate("SELECT * FROM users /* injected */")


class TestValidQueries:
    """Tests that valid SELECT queries pass through."""

    def test_simple_select_passes(self):
        """A simple SELECT should pass validation."""
        validate("SELECT * FROM users")  # Should not raise

    def test_select_with_where_passes(self):
        """SELECT with WHERE clause should pass validation."""
        validate("SELECT id, name FROM users WHERE id = 1")

    def test_select_with_join_passes(self):
        """SELECT with JOIN should pass validation."""
        validate(
            "SELECT u.name, p.name FROM users u "
            "JOIN subscriptions s ON u.id = s.user_id "
            "JOIN plans p ON s.plan_id = p.id"
        )

    def test_select_with_aggregation_passes(self):
        """SELECT with GROUP BY and aggregate functions should pass."""
        validate("SELECT status, COUNT(*) FROM subscriptions GROUP BY status")

    def test_empty_sql_rejected(self):
        """Empty SQL string should raise ForbiddenQueryError."""
        with pytest.raises(ForbiddenQueryError):
            validate("")
        with pytest.raises(ForbiddenQueryError):
            validate("   ")
