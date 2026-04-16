# Hex Analytics Bot — Demo

> A small **agentic analytics bot** in the spirit of Hex's Fall 2025 launch.
> Ask a plain-English question; it writes SQL, runs it, charts the result,
> and answers in your browser or in Slack.

**[ Live demo →   `<paste-render-url-here>` ]**   ·   **[ 90-sec video →   `<paste-loom-url-here>` ]**

![demo screenshot — replace with a real PNG/GIF](docs/demo.png)

---

## Why this maps to Hex

Hex's 2025 product direction is *"agents for analytics, for teams"* — putting a
notebook-grade analyst into Slack, Threads, and the browser so non-technical
people can query the warehouse in plain English. This bot is a tiny working
version of that surface area:

- **Plain-English in, SQL + chart out.** Same shape as Hex's Notebook Agent and
  Threads.
- **Slack-native delivery.** Mirrors the Neo customer pattern of "insights where
  they work."
- **Semantic-layer enrichment.** A small business glossary (MRR, ARR, churn,
  DAU, MAU, …) is injected into every prompt so the LLM speaks SaaS, not raw
  schema.
- **Self-correcting SQL retries.** If the first SQL fails, the error is fed
  back to the LLM for a fix — bounded, observable, no infinite loops.

It is intentionally MVP. It is not trying to replace Hex; it is trying to
demonstrate that I think about the same problems your team is shipping.

---

## Try it in 60 seconds

**The hosted demo** is a one-click experience: open the link above, click a
sample question, get an answer + chart in your browser. Nothing to install.

**To run locally** (web UI):

```bash
git clone <this-repo> && cd Hex
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
uv sync --extra dev
uv run python web_main.py
# open http://localhost:8000
```

That's it. Mock SaaS data is seeded into in-memory SQLite at startup.

To run the **Slack** version locally, see [`docs/slack-setup.md`](#slack-setup)
at the bottom.

---

## What it does

```
                ┌────────────┐         ┌────────────┐
   Browser ────▶│   web/     │────┐    │ gateway/   │◀──── Slack
                │ FastAPI    │    │    │ Bolt+Sock  │
                └────────────┘    │    └────────────┘
                                  ▼          │
                            ┌──────────────────┐
                            │  app/orchestrator │   ← only place that
                            │  compute_answer() │     wires modules
                            └──────────────────┘
                                  │       │
                       ┌──────────┘       └──────────┐
                       ▼                             ▼
                ┌────────────┐               ┌────────────┐
                │  brain/    │──── SQL ────▶ │   db/      │
                │ Claude +   │               │ SQLite     │
                │ retry loop │◀── error ──── │ read-only  │
                └────────────┘               └────────────┘
                       │
                       ▼
                ┌────────────┐
                │   viz/     │   PNG bytes
                │ matplotlib │ ──────────────▶ response
                └────────────┘
```

End-to-end pipeline for one question:

1. **Browser or Slack** sends the question to `web/` or `gateway/`.
2. The respective adapter calls `AppOrchestrator.compute_answer(question)`.
3. **Brain** pulls the schema from DB, enriches it with a SaaS glossary,
   prompts Claude, and gets back `{sql, explanation, suggested_chart}`.
4. **Validator** rejects any non-`SELECT` SQL before it reaches the DB.
5. **DB** runs the query in-memory (synchronous; the orchestrator wraps
   it in `asyncio.to_thread` so the event loop never blocks).
6. If the SQL errors, Brain retries up to N times, feeding the error back
   to the LLM for correction.
7. **Viz** renders the chart to PNG bytes (also wrapped in
   `asyncio.to_thread`).
8. The adapter formats the response: JSON for the browser, in-thread reply
   + file upload for Slack.

---

## Architecture — six isolated modules

| Module | Role | Async / Sync |
|--------|------|--------------|
| `shared/` | Canonical dataclasses, enums, ABC interfaces, error hierarchy | n/a |
| `db/` | SQLite engine, schema + seed, write-operation sanitizer | sync |
| `viz/` | Matplotlib chart engine, 9 chart types, auto-inference | sync |
| `brain/` | Anthropic client, semantic layer, retry loop, prompt templates | async |
| `gateway/` | Slack Bolt + Socket Mode, dedup, rate limiter | async |
| `web/` | FastAPI server, single-page UI, JSON `/api/ask` | async |
| `app/` | Orchestrator — the **only** file that wires modules together | async |

**Strict boundary rule:** no module imports from another module's internals.
Every cross-module call goes through the public interfaces in
`shared/interfaces.py`. The orchestrator is the single adapter; both `gateway/`
and `web/` are thin shells over `AppOrchestrator.compute_answer()`.

This means the same brain pipeline drives Slack and the browser with zero
duplication.

---

## Tech stack

| Concern | Choice |
|--------|--------|
| LLM | Anthropic Claude (Sonnet 4.6 by default; configurable via `CLAUDE_MODEL`) |
| Web framework | FastAPI + uvicorn |
| Slack | `slack-bolt` Async + Socket Mode (no public webhook needed) |
| Database | SQLite in-memory, seeded deterministically with Faker (`seed=42`) |
| Charting | matplotlib + seaborn, Agg backend (thread-safe for async) |
| Config | pydantic-settings |
| Testing | pytest, pytest-asyncio, FastAPI TestClient |
| Package mgmt | uv |
| Deploy | Docker + Render Blueprint (`render.yaml`) |

---

## Tests

137 tests across the six modules. Run:

```bash
uv run pytest src/hex
```

Coverage breakdown:

- `db/` — engine, sanitizer, seed determinism
- `viz/` — engine, chart-type inference, per-chart renderers
- `brain/` — orchestrator, LLM client, retry loop, semantic layer, SQL validator
- `gateway/` — router, request parser, dedup, rate limiter, response sender
- `web/` — endpoints, input validation, timeout guard, error paths
- `app/` — orchestrator integration + e2e flow with real DB and viz

---

## Mock dataset

In-memory SQLite re-seeds on every cold start (`seed=42`, deterministic):

| Table | Rows | Description |
|-------|------|-------------|
| `plans` | 3 | Starter ($29), Professional ($99), Enterprise ($299) |
| `users` | 50 | Customer accounts with roles |
| `subscriptions` | 60 | User-plan links with status tracking |
| `invoices` | ~200 | Billing records |
| `events` | 500 | User activity (logins, page views, etc.) |

Sample questions the demo handles well:

- "Show monthly revenue by plan"
- "How many users signed up last month?"
- "Top 10 customers by total spend"
- "Daily active users over time"
- "What's the churn rate by plan?"

---

## What's next (intentionally not in this MVP)

Honest scoping. None of these are hard given the existing architecture; they
were left out so the demo stays one weekend's work.

- **Multi-turn / thread memory.** Right now every question is single-shot.
  Real users follow up ("now break that down by region"). Brain needs a
  conversation-history store.
- **Real warehouse adapter.** The `DatabaseEngineInterface` is already there;
  swap `SQLiteEngine` for a Postgres or Snowflake adapter and the rest of
  the system doesn't change.
- **Auth on the web UI.** The hosted demo is unauthenticated — anyone with
  the link can ask questions and burn API budget. Fine for a demo, not
  fine for prod.
- **Proper observability.** Today the orchestrator logs latency per
  pipeline; OpenTelemetry traces would make it easier to see where time
  goes (LLM vs DB vs viz).
- **Caching.** Same question asked twice = two LLM calls. A small
  `(question_hash → BrainResponse)` cache would cut cost ~50% on a demo.
- **Performance benchmark.** No baseline. Cold-start latency is ~3s, warm
  is ~5–10s end-to-end on the free Render tier.

---

## Slack setup

<details>
<summary>Click to expand — Slack-native usage (optional)</summary>

The Slack flow is the more architecturally interesting surface but takes ~10
minutes to set up because of Slack app config. The web demo above shows the
same pipeline with no Slack required.

### Prereqs

- A Slack workspace where you can install apps
- `SLACK_BOT_TOKEN` (xoxb-…) and `SLACK_APP_TOKEN` (xapp-…) — Socket Mode

### Steps

1. Create a Slack app at <https://api.slack.com/apps> → "From scratch"
2. **Socket Mode**: enable, generate an app-level token with `connections:write`
3. **OAuth scopes**: `app_mentions:read`, `chat:write`, `files:write`,
   `reactions:write`
4. **Event subscriptions**: subscribe to `app_mention`
5. Install the app to your workspace, copy bot token + app token
6. Add both to `.env`:

   ```
   SLACK_BOT_TOKEN=xoxb-...
   SLACK_APP_TOKEN=xapp-...
   ANTHROPIC_API_KEY=sk-ant-...
   ```

7. Run:

   ```bash
   uv run python main.py
   ```

8. In Slack, mention the bot: `@YourBot how many users signed up last month?`

</details>

---

## Repo layout

```
src/hex/
  shared/      canonical types, interfaces, errors
  db/          sqlite engine + schema + seed + sanitizer
  viz/         matplotlib chart engine + inference
  brain/       claude client + semantic layer + retry loop
  gateway/     slack bolt + dedup + rate limiter
  web/         fastapi server + single-page UI
  app/         orchestrator (the one and only adapter)
main.py        slack entrypoint
web_main.py    web entrypoint
Dockerfile     production container
render.yaml    one-click Render deploy
```

---

Built as a portfolio project. Feedback welcome.
