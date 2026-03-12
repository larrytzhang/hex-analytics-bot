"""Deterministic seed data for the mock SaaS analytics database.

Uses Faker with a fixed seed (42) so every engine instance produces
identical data. Populates: 3 plans, 50 users, 60 subscriptions,
~200 invoices, ~500 events.

A _meta table prevents double-seeding if called multiple times.
"""

import random
import sqlite3
from datetime import datetime, timedelta

from faker import Faker

# Fixed seed for deterministic output
RANDOM_SEED = 42


def seed_database(conn: sqlite3.Connection) -> None:
    """Populate all tables with deterministic mock data.

    Uses Faker(seed=42) and random.seed(42) for reproducibility.
    Creates a _meta table with a 'seeded' flag to prevent double-seeding.

    Args:
        conn: An active SQLite connection with tables already created.
    """
    cursor = conn.cursor()

    # ── Guard: prevent double-seeding ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS _meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    cursor.execute("SELECT value FROM _meta WHERE key = 'seeded'")
    if cursor.fetchone():
        return  # Already seeded

    fake = Faker()
    Faker.seed(RANDOM_SEED)
    random.seed(RANDOM_SEED)

    # ── Seed plans (3 tiers) ──
    plans = [
        ("Starter", 29.0, 5),
        ("Professional", 99.0, 25),
        ("Enterprise", 299.0, 100),
    ]
    for name, price, seats in plans:
        cursor.execute(
            "INSERT INTO plans (name, price_monthly, max_seats, created_at) VALUES (?, ?, ?, ?)",
            (name, price, seats, "2024-01-01T00:00:00"),
        )

    # ── Seed users (50) ──
    base_date = datetime(2024, 1, 15)
    for i in range(50):
        created = base_date + timedelta(days=random.randint(0, 365))
        last_login = created + timedelta(days=random.randint(1, 180))
        role = random.choice(["user", "user", "user", "admin", "viewer"])
        cursor.execute(
            """INSERT INTO users (email, name, company, role, created_at, last_login_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                fake.unique.email(),
                fake.name(),
                fake.company(),
                role,
                created.isoformat(),
                last_login.isoformat(),
            ),
        )

    # ── Seed subscriptions (60) ──
    statuses = ["active", "active", "active", "active", "churned", "paused"]
    for i in range(60):
        user_id = random.randint(1, 50)
        plan_id = random.randint(1, 3)
        plan_price = plans[plan_id - 1][1]
        status = random.choice(statuses)
        started = base_date + timedelta(days=random.randint(0, 300))
        ended = (
            (started + timedelta(days=random.randint(30, 180))).isoformat()
            if status == "churned"
            else None
        )
        cursor.execute(
            """INSERT INTO subscriptions (user_id, plan_id, status, started_at, ended_at, mrr)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, plan_id, status, started.isoformat(), ended, plan_price),
        )

    # ── Seed invoices (~200) ──
    invoice_statuses = ["paid", "paid", "paid", "paid", "pending", "overdue"]
    for sub_id in range(1, 61):
        plan_id_for_sub = random.randint(1, 3)
        amount = plans[plan_id_for_sub - 1][1]
        num_invoices = random.randint(1, 6)
        for j in range(num_invoices):
            issued = base_date + timedelta(days=30 * j + random.randint(0, 10))
            inv_status = random.choice(invoice_statuses)
            paid = (
                (issued + timedelta(days=random.randint(0, 15))).isoformat()
                if inv_status == "paid"
                else None
            )
            cursor.execute(
                """INSERT INTO invoices (subscription_id, amount, currency, status, issued_at, paid_at)
                   VALUES (?, ?, 'USD', ?, ?, ?)""",
                (sub_id, amount, inv_status, issued.isoformat(), paid),
            )

    # ── Seed events (~500) ──
    event_types = [
        "login",
        "page_view",
        "query_run",
        "chart_created",
        "export",
        "invite_sent",
        "settings_changed",
        "logout",
    ]
    for _ in range(500):
        user_id = random.randint(1, 50)
        event_type = random.choice(event_types)
        event_data = f'{{"source": "{random.choice(["web", "api", "mobile"])}"}}'
        created = base_date + timedelta(
            days=random.randint(0, 365),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
        )
        cursor.execute(
            """INSERT INTO events (user_id, event_type, event_data, created_at)
               VALUES (?, ?, ?, ?)""",
            (user_id, event_type, event_data, created.isoformat()),
        )

    # ── Mark as seeded ──
    cursor.execute("INSERT INTO _meta (key, value) VALUES ('seeded', 'true')")
    conn.commit()
