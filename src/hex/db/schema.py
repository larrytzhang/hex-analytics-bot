"""Database schema definitions for the mock SaaS analytics database.

Defines the DDL for 5 tables representing a typical SaaS business:
users, plans, subscriptions, invoices, and events.
Called once at engine initialization to set up the in-memory SQLite DB.
"""

import sqlite3


def create_tables(conn: sqlite3.Connection) -> None:
    """Create all database tables for the mock SaaS analytics schema.

    Creates 5 tables: plans, users, subscriptions, invoices, and events.
    Uses IF NOT EXISTS to be safely idempotent.

    Args:
        conn: An active SQLite connection to create tables on.
    """
    cursor = conn.cursor()

    # ── Plans table: subscription tier definitions ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            price_monthly REAL NOT NULL,
            max_seats INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # ── Users table: customer accounts ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            company TEXT,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            last_login_at TEXT
        )
    """)

    # ── Subscriptions table: links users to plans with status tracking ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            plan_id INTEGER NOT NULL REFERENCES plans(id),
            status TEXT NOT NULL DEFAULT 'active',
            started_at TEXT NOT NULL,
            ended_at TEXT,
            mrr REAL NOT NULL
        )
    """)

    # ── Invoices table: billing records per subscription ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscription_id INTEGER NOT NULL REFERENCES subscriptions(id),
            amount REAL NOT NULL,
            currency TEXT NOT NULL DEFAULT 'USD',
            status TEXT NOT NULL DEFAULT 'paid',
            issued_at TEXT NOT NULL,
            paid_at TEXT
        )
    """)

    # ── Events table: user activity tracking ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            event_type TEXT NOT NULL,
            event_data TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
