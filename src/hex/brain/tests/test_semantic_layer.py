"""Tests for the semantic layer.

Verifies that enrich() produces valid SemanticContext with
descriptions for all 5 tables and a populated business glossary.
"""

from hex.brain.semantic_layer import enrich
from hex.shared.models import SemanticContext


class TestSemanticLayer:
    """Tests for the enrich() function."""

    def _get_raw_schema(self) -> dict[str, list[dict[str, str]]]:
        """Helper to create a raw schema matching the mock DB."""
        return {
            "plans": [
                {"name": "id", "type": "INTEGER"},
                {"name": "name", "type": "TEXT"},
                {"name": "price_monthly", "type": "REAL"},
                {"name": "max_seats", "type": "INTEGER"},
                {"name": "created_at", "type": "TEXT"},
            ],
            "users": [
                {"name": "id", "type": "INTEGER"},
                {"name": "email", "type": "TEXT"},
                {"name": "name", "type": "TEXT"},
                {"name": "company", "type": "TEXT"},
                {"name": "role", "type": "TEXT"},
                {"name": "created_at", "type": "TEXT"},
                {"name": "last_login_at", "type": "TEXT"},
            ],
            "subscriptions": [
                {"name": "id", "type": "INTEGER"},
                {"name": "user_id", "type": "INTEGER"},
                {"name": "plan_id", "type": "INTEGER"},
                {"name": "status", "type": "TEXT"},
                {"name": "started_at", "type": "TEXT"},
                {"name": "ended_at", "type": "TEXT"},
                {"name": "mrr", "type": "REAL"},
            ],
            "invoices": [
                {"name": "id", "type": "INTEGER"},
                {"name": "subscription_id", "type": "INTEGER"},
                {"name": "amount", "type": "REAL"},
                {"name": "currency", "type": "TEXT"},
                {"name": "status", "type": "TEXT"},
                {"name": "issued_at", "type": "TEXT"},
                {"name": "paid_at", "type": "TEXT"},
            ],
            "events": [
                {"name": "id", "type": "INTEGER"},
                {"name": "user_id", "type": "INTEGER"},
                {"name": "event_type", "type": "TEXT"},
                {"name": "event_data", "type": "TEXT"},
                {"name": "created_at", "type": "TEXT"},
            ],
        }

    def test_returns_semantic_context(self):
        """enrich() should return a SemanticContext instance."""
        result = enrich(self._get_raw_schema())
        assert isinstance(result, SemanticContext)

    def test_all_five_tables_have_descriptions(self):
        """All 5 tables should have non-empty descriptions."""
        result = enrich(self._get_raw_schema())
        table_names = {t.name for t in result.tables}
        assert table_names == {"plans", "users", "subscriptions", "invoices", "events"}

        for table in result.tables:
            assert table.description, f"Table '{table.name}' has no description"

    def test_columns_have_descriptions(self):
        """Every column in every table should have a description."""
        result = enrich(self._get_raw_schema())
        for table in result.tables:
            for col in table.columns:
                assert col.description, f"Column '{table.name}.{col.name}' has no description"

    def test_dialect_is_sqlite(self):
        """The dialect should be 'sqlite'."""
        result = enrich(self._get_raw_schema())
        assert result.dialect == "sqlite"

    def test_business_glossary_populated(self):
        """The business glossary should contain key SaaS terms."""
        result = enrich(self._get_raw_schema())
        assert "MRR" in result.business_glossary
        assert "churn" in result.business_glossary
        assert "ARR" in result.business_glossary
