# Hex Agentic Analytics Slack Bot

An AI-powered Slack bot that answers data questions in plain English. Ask it a question, and it generates SQL via Claude, executes it against a mock SaaS database, visualizes the results, and replies in-thread with a text summary + chart.

## Architecture

```
Slack -> Gateway -> Orchestrator -> Brain -> DB (SQLite)
                        |                      |
                        +----> Viz (matplotlib) +
```

**6 isolated modules** with strict boundaries — modules never import from each other:

| Module | Role | Async/Sync |
|--------|------|------------|
| `shared/` | Canonical types, interfaces (ABCs), errors | N/A |
| `db/` | SQLite engine, schema, seed data, sanitizer | Sync |
| `viz/` | Chart engine, 5 chart types, inference | Sync |
| `brain/` | LLM client, semantic layer, SQL retry loop | Async |
| `gateway/` | Slack Bolt, event parsing, dedup, rate limiting | Async |
| `app/` | Orchestrator — the sole adapter wiring everything | Async |

## Setup

### Prerequisites
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Slack Bot + App tokens (Socket Mode)
- Anthropic API key

### Install

```bash
uv sync --all-extras
```

### Configure

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

Required environment variables:
- `SLACK_BOT_TOKEN` — Bot OAuth token (xoxb-...)
- `SLACK_APP_TOKEN` — App token for Socket Mode (xapp-...)
- `ANTHROPIC_API_KEY` — Claude API key

### Run

```bash
uv run python main.py
```

### Test

```bash
uv run pytest -v
```

## Mock Database

The bot runs against an in-memory SQLite database with deterministic seed data:

| Table | Rows | Description |
|-------|------|-------------|
| `plans` | 3 | Starter ($29), Professional ($99), Enterprise ($299) |
| `users` | 50 | Customer accounts with roles |
| `subscriptions` | 60 | User-plan links with status tracking |
| `invoices` | ~200 | Billing records |
| `events` | 500 | User activity (logins, page views, etc.) |

## Example Questions

- "How many users signed up last month?"
- "Show me revenue by plan"
- "What's the churn rate?"
- "Which users are most active?"
- "Compare MRR across plan tiers"
