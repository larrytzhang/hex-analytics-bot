"""Semantic layer for enriching raw database schema.

Transforms the raw schema dict from the DB engine into a rich
SemanticContext with table descriptions, column descriptions,
sample values, and a business glossary for the LLM prompt.
"""

from hex.shared.models import ColumnMeta, SemanticContext, TableMeta


# ── Hardcoded enrichment for the mock SaaS database's 5 tables ──

_TABLE_DESCRIPTIONS: dict[str, str] = {
    "plans": "Subscription tier definitions (Starter, Professional, Enterprise) with pricing and seat limits.",
    "users": "Customer accounts with email, name, company, role, and login tracking.",
    "subscriptions": "Links users to plans with status tracking (active, churned, paused) and MRR.",
    "invoices": "Billing records per subscription with amount, currency, status, and payment dates.",
    "events": "User activity tracking including logins, page views, queries, chart creation, and exports.",
}

_COLUMN_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "plans": {
        "id": "Auto-incrementing primary key.",
        "name": "Plan tier name: 'Starter', 'Professional', or 'Enterprise'.",
        "price_monthly": "Monthly price in USD for this plan tier.",
        "max_seats": "Maximum number of user seats allowed on this plan.",
        "created_at": "ISO 8601 timestamp when the plan was created.",
    },
    "users": {
        "id": "Auto-incrementing primary key.",
        "email": "Unique email address for the user account.",
        "name": "Full name of the user.",
        "company": "Company name the user belongs to.",
        "role": "User role: 'user', 'admin', or 'viewer'.",
        "created_at": "ISO 8601 timestamp when the account was created.",
        "last_login_at": "ISO 8601 timestamp of the most recent login.",
    },
    "subscriptions": {
        "id": "Auto-incrementing primary key.",
        "user_id": "Foreign key to users.id.",
        "plan_id": "Foreign key to plans.id.",
        "status": "Subscription status: 'active', 'churned', or 'paused'.",
        "started_at": "ISO 8601 timestamp when the subscription began.",
        "ended_at": "ISO 8601 timestamp when the subscription ended (NULL if active).",
        "mrr": "Monthly Recurring Revenue in USD for this subscription.",
    },
    "invoices": {
        "id": "Auto-incrementing primary key.",
        "subscription_id": "Foreign key to subscriptions.id.",
        "amount": "Invoice amount in the specified currency.",
        "currency": "Three-letter currency code (always 'USD' in this dataset).",
        "status": "Invoice status: 'paid', 'pending', or 'overdue'.",
        "issued_at": "ISO 8601 timestamp when the invoice was issued.",
        "paid_at": "ISO 8601 timestamp when the invoice was paid (NULL if unpaid).",
    },
    "events": {
        "id": "Auto-incrementing primary key.",
        "user_id": "Foreign key to users.id.",
        "event_type": "Type of event: 'login', 'page_view', 'query_run', 'chart_created', 'export', 'invite_sent', 'settings_changed', 'logout'.",
        "event_data": "JSON string with additional event metadata (e.g. source: web/api/mobile).",
        "created_at": "ISO 8601 timestamp when the event occurred.",
    },
}

_BUSINESS_GLOSSARY: dict[str, str] = {
    "MRR": "Monthly Recurring Revenue — the monthly price of a user's active subscription. Stored in subscriptions.mrr.",
    "ARR": "Annual Recurring Revenue — MRR * 12.",
    "churn": "When a subscription status becomes 'churned' (ended_at is set).",
    "active user": "A user with at least one subscription where status = 'active'.",
    "sign up": "When a new user record is created (users.created_at).",
    "revenue": "Total invoiced amount — SUM of invoices.amount where status = 'paid'.",
    "DAU": "Daily Active Users — distinct users with events on a given day.",
    "MAU": "Monthly Active Users — distinct users with events in a given month.",
    "conversion": "When a user creates a subscription after signing up.",
    "ARPU": "Average Revenue Per User — total revenue / number of active users.",
}


def enrich(raw_schema: dict[str, list[dict[str, str]]]) -> SemanticContext:
    """Enrich a raw database schema into a full SemanticContext.

    Transforms the raw dict from DatabaseEngineInterface.get_schema_description()
    into a rich SemanticContext with table descriptions, column descriptions,
    and a business glossary for injection into the LLM prompt.

    Args:
        raw_schema: Dict mapping table names to lists of column dicts
                    (each with 'name' and 'type' keys).

    Returns:
        SemanticContext with enriched metadata for all tables.
    """
    tables: list[TableMeta] = []

    for table_name, columns in raw_schema.items():
        col_descs = _COLUMN_DESCRIPTIONS.get(table_name, {})
        enriched_columns: list[ColumnMeta] = []

        for col in columns:
            col_name = col["name"]
            col_type = col["type"]
            description = col_descs.get(col_name, f"Column '{col_name}' of type {col_type}.")

            enriched_columns.append(
                ColumnMeta(
                    name=col_name,
                    dtype=col_type,
                    description=description,
                )
            )

        table_desc = _TABLE_DESCRIPTIONS.get(
            table_name, f"Table '{table_name}'."
        )
        tables.append(
            TableMeta(
                name=table_name,
                description=table_desc,
                columns=enriched_columns,
            )
        )

    return SemanticContext(
        tables=tables,
        dialect="sqlite",
        business_glossary=_BUSINESS_GLOSSARY,
    )
