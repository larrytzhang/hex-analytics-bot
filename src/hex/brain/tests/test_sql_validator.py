"""Tests for the Brain's SQL validator.

Verifies that write operations raise WriteOperationDetected
and valid SELECT queries pass through.
"""

import pytest

from hex.brain.sql_validator import check
from hex.shared.errors import WriteOperationDetected


class TestSQLValidator:
    """Tests for the check() function."""

    @pytest.mark.parametrize("sql", [
        "INSERT INTO users VALUES (1, 'a')",
        "UPDATE users SET name = 'x'",
        "DELETE FROM users WHERE id = 1",
        "DROP TABLE users",
        "ALTER TABLE users ADD COLUMN x TEXT",
        "CREATE TABLE evil (id INTEGER)",
        "TRUNCATE TABLE users",
    ])
    def test_write_operations_raise_error(self, sql):
        """Write operations should raise WriteOperationDetected."""
        with pytest.raises(WriteOperationDetected):
            check(sql)

    def test_valid_select_passes(self):
        """A valid SELECT should not raise any error."""
        check("SELECT * FROM users")  # Should not raise

    def test_empty_sql_passes(self):
        """Empty/None SQL should pass (handled upstream)."""
        check("")  # Should not raise
        check(None)  # Should not raise

    def test_case_insensitive_detection(self):
        """Write keywords should be caught regardless of case."""
        with pytest.raises(WriteOperationDetected):
            check("drop TABLE users")
