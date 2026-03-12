"""Tests for the SQLiteEngine implementation.

Verifies query execution, schema description, and health check
functionality of the database engine.
"""

import pytest

from hex.db.engine import SQLiteEngine
from hex.shared.errors import ForbiddenQueryError, QueryExecutionError


@pytest.fixture
def engine():
    """Create a fresh SQLiteEngine instance for each test."""
    return SQLiteEngine()


class TestExecuteReadonly:
    """Tests for the execute_readonly method."""

    def test_select_returns_correct_columns(self, engine):
        """SELECT query should return correct column names."""
        result = engine.execute_readonly("SELECT id, name, price_monthly FROM plans")
        assert result.success is True
        assert result.columns == ["id", "name", "price_monthly"]

    def test_select_returns_correct_row_count(self, engine):
        """SELECT query should return the correct number of rows."""
        result = engine.execute_readonly("SELECT * FROM plans")
        assert result.success is True
        assert result.row_count == 3  # 3 seeded plans

    def test_select_returns_tuple_rows(self, engine):
        """Rows should be tuples, not lists or dicts."""
        result = engine.execute_readonly("SELECT name FROM plans LIMIT 1")
        assert isinstance(result.rows[0], tuple)

    def test_select_users_count(self, engine):
        """Users table should have 50 seeded rows."""
        result = engine.execute_readonly("SELECT COUNT(*) as cnt FROM users")
        assert result.success is True
        assert result.rows[0][0] == 50

    def test_write_operations_blocked(self, engine):
        """INSERT/UPDATE/DELETE should raise ForbiddenQueryError."""
        with pytest.raises(ForbiddenQueryError):
            engine.execute_readonly("INSERT INTO users (email, name) VALUES ('a', 'b')")

    def test_invalid_column_raises_execution_error(self, engine):
        """Querying a nonexistent column should raise QueryExecutionError."""
        with pytest.raises(QueryExecutionError):
            engine.execute_readonly("SELECT nonexistent_column FROM plans")

    def test_query_result_to_dicts(self, engine):
        """to_dicts() should convert rows to list of dicts."""
        result = engine.execute_readonly("SELECT id, name FROM plans LIMIT 1")
        dicts = result.to_dicts()
        assert len(dicts) == 1
        assert "id" in dicts[0]
        assert "name" in dicts[0]


class TestGetSchemaDescription:
    """Tests for the get_schema_description method."""

    def test_returns_all_tables(self, engine):
        """Schema should include all 5 business tables."""
        schema = engine.get_schema_description()
        expected_tables = {"plans", "users", "subscriptions", "invoices", "events"}
        assert expected_tables == set(schema.keys())

    def test_columns_have_name_and_type(self, engine):
        """Each column entry should have 'name' and 'type' keys."""
        schema = engine.get_schema_description()
        for table_name, columns in schema.items():
            for col in columns:
                assert "name" in col, f"Missing 'name' in {table_name}"
                assert "type" in col, f"Missing 'type' in {table_name}"

    def test_plans_table_columns(self, engine):
        """Plans table should have the expected columns."""
        schema = engine.get_schema_description()
        col_names = [c["name"] for c in schema["plans"]]
        assert "id" in col_names
        assert "name" in col_names
        assert "price_monthly" in col_names
        assert "max_seats" in col_names


class TestHealthCheck:
    """Tests for the health_check method."""

    def test_health_check_returns_true(self, engine):
        """Health check should return True on a properly initialized engine."""
        assert engine.health_check() is True
