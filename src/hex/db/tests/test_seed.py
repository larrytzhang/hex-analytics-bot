"""Tests for the database seed data.

Verifies that seed data is deterministic and row counts match
expectations.
"""

import pytest

from hex.db.engine import SQLiteEngine


@pytest.fixture
def engine():
    """Create a fresh SQLiteEngine instance for each test."""
    return SQLiteEngine()


class TestRowCounts:
    """Tests that seeded data matches expected counts."""

    def test_plans_count(self, engine):
        """Plans table should have exactly 3 rows."""
        result = engine.execute_readonly("SELECT COUNT(*) FROM plans")
        assert result.rows[0][0] == 3

    def test_users_count(self, engine):
        """Users table should have exactly 50 rows."""
        result = engine.execute_readonly("SELECT COUNT(*) FROM users")
        assert result.rows[0][0] == 50

    def test_subscriptions_count(self, engine):
        """Subscriptions table should have exactly 60 rows."""
        result = engine.execute_readonly("SELECT COUNT(*) FROM subscriptions")
        assert result.rows[0][0] == 60

    def test_invoices_count_approximate(self, engine):
        """Invoices table should have roughly 200 rows (varies by random)."""
        result = engine.execute_readonly("SELECT COUNT(*) FROM invoices")
        count = result.rows[0][0]
        assert 100 <= count <= 400, f"Expected ~200 invoices, got {count}"

    def test_events_count(self, engine):
        """Events table should have exactly 500 rows."""
        result = engine.execute_readonly("SELECT COUNT(*) FROM events")
        assert result.rows[0][0] == 500


class TestDeterminism:
    """Tests that seed data is deterministic across instances."""

    def test_two_engines_produce_identical_data(self):
        """Two engines with same seed should produce identical user data."""
        engine1 = SQLiteEngine()
        engine2 = SQLiteEngine()

        result1 = engine1.execute_readonly("SELECT email, name FROM users ORDER BY id")
        result2 = engine2.execute_readonly("SELECT email, name FROM users ORDER BY id")

        assert result1.rows == result2.rows

    def test_plan_names_are_correct(self, engine):
        """Plan names should be Starter, Professional, Enterprise."""
        result = engine.execute_readonly("SELECT name FROM plans ORDER BY id")
        names = [row[0] for row in result.rows]
        assert names == ["Starter", "Professional", "Enterprise"]

    def test_plan_prices_are_correct(self, engine):
        """Plan prices should match the seeded values."""
        result = engine.execute_readonly(
            "SELECT name, price_monthly FROM plans ORDER BY id"
        )
        prices = {row[0]: row[1] for row in result.rows}
        assert prices == {
            "Starter": 29.0,
            "Professional": 99.0,
            "Enterprise": 299.0,
        }
