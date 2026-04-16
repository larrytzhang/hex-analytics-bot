# Hex Bot — Demo-Ready Plan

**Goal:** Make this codebase trivially demo-able to Hex leadership via (a) one clickable browser link and (b) a 90-second recorded video of the Slack flow.

**Scope:** Demo-critical only. Multi-turn, Postgres swap, OTel, etc. are deferred to a "What's Next" section in the README.

**Estimated effort:** ~6 hours of Claude work + ~1 hour of Larry's manual work.

---

## Phase 1 — Repo cleanup (15 min)

- [ ] Delete `nextsteps.txt` (working notes, not for portfolio).
- [ ] Delete duplicate `plans folder/` directory (the `plans/` deletion in git status is the canonical one — old planning docs do not belong in a portfolio repo).
- [ ] Stage or revert the README.md change in git status so `git status` is clean before Phase 5 rewrite.
- [ ] Add a `tasks/lessons.md` stub (empty header) to satisfy CLAUDE.md §7.
- [ ] Commit: `chore: repo cleanup before demo prep`.

---

## Phase 2 — Refactor orchestrator: separate compute from delivery (1.5 hr)

**Why:** The web UI needs the same brain → viz pipeline as Slack. Today, `AppOrchestrator.handle_question` is hardcoded to return `SlackResponse` and uploads the chart inline. Extract a transport-agnostic compute step so both Slack and Web can call it.

- [ ] Add `AnswerResult` dataclass to `src/hex/shared/models.py`:
  - `text_summary: str`
  - `query_result: QueryResult | None`
  - `chart_bytes: bytes | None`
  - `chart_mime: str` (default `"image/png"`)
  - `error: str | None`
- [ ] Add `_compute_answer(question: str) -> AnswerResult` to `AppOrchestrator`. Pure compute — no Slack calls.
- [ ] Refactor `handle_question(SlackRequest) -> SlackResponse` to call `_compute_answer`, then handle Slack-specific delivery (file upload, thread reply).
- [ ] Update `OrchestratorInterface` in `shared/interfaces.py` to expose both methods.
- [ ] Add 4 unit tests in `src/hex/app/tests/test_compute_answer.py`:
  - Success path (text + chart bytes returned).
  - Brain raises `BrainError` → `AnswerResult.error` set, no crash.
  - Viz raises `VisualizationError` → text returned, `chart_bytes=None`.
  - Brain returns `suggested_chart=NONE` → text returned, no chart attempted.
- [ ] All existing 120 tests still pass.
- [ ] Commit: `refactor: extract _compute_answer from AppOrchestrator for transport-agnostic reuse`.

**Architectural justification:** Keeps `app/orchestrator.py` as the only adapter between modules per CLAUDE.md §1. Web/ becomes a sibling I/O surface to gateway/, not a new orchestrator.

---

## Phase 3 — Build the web module `src/hex/web/` (2.5 hr)

**Goal:** One clickable link. User types a question, gets text + table + chart in <10 sec.

### Files to create

- `src/hex/web/__init__.py` — public exports.
- `src/hex/web/config.py` — Pydantic `WebConfig` (HOST, PORT, defaults to 0.0.0.0:8000).
- `src/hex/web/server.py` — FastAPI app factory `create_app(orchestrator: AppOrchestrator) -> FastAPI`:
  - `GET /` → serve `static/index.html`.
  - `GET /healthz` → `{"status": "ok"}` (for Render health checks).
  - `POST /api/ask` → body `{question: str}` → returns JSON `{text, table_md, chart_b64, error}`.
  - Calls `orchestrator._compute_answer(question)` (wrap in `asyncio.create_task` for timeout safety).
  - 30-second request timeout. On timeout, return `{error: "Question took too long, try a simpler one."}`.
  - 422 if question empty or >500 chars.
- `src/hex/web/static/index.html` — single page, no build step:
  - Tailwind via CDN for clean styling.
  - Header with "Hex Analytics Bot — Demo" title and a banner: "Uses mock SaaS data (5 tables: plans, users, subscriptions, invoices, events)."
  - Input box + "Ask" button.
  - 4 sample-question pill buttons that pre-fill the input ("Show revenue by plan", "How many users signed up last month?", "Top 10 customers by spend", "Daily active users over time").
  - Result panel: text summary, markdown table rendered (use `marked.js` CDN), chart `<img>` from base64.
  - Loading spinner while waiting.
  - "Ask another" button to reset.
- `src/hex/web/tests/test_server.py` — 5 tests:
  - `POST /api/ask` happy path returns 200 with text + chart_b64.
  - Empty question → 422.
  - Question >500 chars → 422.
  - Brain error → 200 with `error` field set (graceful, not 500).
  - `GET /healthz` → 200.

### Entrypoint

- `web_main.py` at repo root — mirrors `main.py` but skips Slack:
  - Wires DB → Brain → Viz → AppOrchestrator (without `slack_client`, pass `None` or a no-op stub).
  - Builds FastAPI app via `create_app(orchestrator)`.
  - Runs uvicorn.

**Note:** `AppOrchestrator.__init__` currently requires `slack_client`. Adjust to `slack_client | None`, document that Slack-only methods will raise if called without it. Add one test for this.

- [ ] Commit: `feat: add web/ module — FastAPI single-page demo UI`.

---

## Phase 4 — Deploy-ready polish (45 min)

- [ ] Add `Dockerfile` (slim Python 3.12, install via uv, runs `web_main.py`, exposes 8000).
- [ ] Add `render.yaml` for one-click Render deploy with `ANTHROPIC_API_KEY` declared as required env var.
- [ ] Add latency logging to `_compute_answer`: `logger.info("Pipeline: brain=%.2fs viz=%.2fs total=%.2fs", ...)`. Cheap observability that reads as production-minded.
- [ ] Style sweep on existing matplotlib charts: apply seaborn theme + larger font + consistent palette so default output looks polished.
- [ ] Commit: `feat: deployable Docker + render.yaml + chart styling polish`.

---

## Phase 5 — README rewrite (45 min)

Rewrite `README.md` with this structure:

1. **One-line pitch + live demo button + embedded GIF/screenshot** (top of file).
2. **"Why this matters to Hex"** — one paragraph mapping the project to Hex's Fall 2025 agentic launch + Slack/Threads integration.
3. **3-line quickstart**: clone, set `ANTHROPIC_API_KEY`, `uv run python web_main.py`.
4. **ASCII architecture diagram** (request flow: Slack/Web → Gateway → AppOrchestrator → Brain → DB → Viz → response).
5. **Module overview** — 6 modules, one line each.
6. **Tech stack table**.
7. **Testing** — `uv run pytest`, coverage stats.
8. **What's next** — single-turn only, in-memory DB, no auth, no OTel. Honest scoping.
9. **Slack setup** — collapsible `<details>` block at the bottom (no longer the headline flow).

- [ ] Commit: `docs: rewrite README around live demo + Hex relevance`.

---

## Phase 6 — Final verification

- [ ] `uv run pytest` — all tests green (~130 expected).
- [ ] `uv run python web_main.py` locally → open `http://localhost:8000`, click each sample question, verify text + table + chart all render.
- [ ] `docker build . && docker run -p 8000:8000 -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY hex-bot` — confirm container runs end-to-end.
- [ ] `git status` clean.
- [ ] Commit: `chore: final verification before deploy`.

---

## What Larry needs to do manually

- [ ] **Pick a host.** Recommended: **Render.com** (free tier, GitHub auto-deploy, supports Python + Docker). Alternatives: Railway, Fly.io.
- [ ] **Create Render account** and connect this repo. Render auto-detects `render.yaml`.
- [ ] **Set env vars on Render dashboard:**
  - `ANTHROPIC_API_KEY` = your key
  - `CLAUDE_MODEL` = `claude-sonnet-4-6` (or whatever you've been testing with)
- [ ] **First deploy.** Grab the public URL (e.g. `hex-bot-xyz.onrender.com`). Paste into the README "live demo" button at top.
- [ ] **Optional but recommended: custom domain** (~$12/yr on Cloudflare Registrar or Namecheap). `hex-demo.larryzhang.dev` reads way more polished than the default Render subdomain.
- [ ] **Record 90-sec demo video.** Use **Loom** (free, instant shareable link) or QuickTime + unlisted YouTube. Script:
  - 0–10s: "I built a small agentic analytics bot inspired by Hex's Fall 2025 launch."
  - 10–30s: Show **web UI** — click a sample question, watch it generate SQL + chart.
  - 30–55s: Show **Slack** — same question, response in-thread with the chart.
  - 55–80s: Quick code tour — 6-module separation, ~130 tests, async/sync boundaries.
  - 80–90s: "Repo + live demo linked below. Would love to chat."
- [ ] **Send to Hex leadership** with a 3-line message:
  - Live demo link.
  - Loom link.
  - GitHub repo link.

---

## Open decisions for Larry to confirm before I start

1. **Web UI style:** single-shot Q&A panel (recommended for MVP) vs. chat-bubble back-and-forth. Multi-turn isn't supported on the backend, so chat bubbles would feel fake. Going with single-shot unless you say otherwise.
2. **"Wow chart":** I'm skipping a multi-panel dashboard chart to stay MVP. Will instead apply seaborn styling to existing chart types so they look polished by default. Add the dashboard later if time allows.
3. **Banner on web demo:** "Uses mock SaaS data" banner so leadership knows what to ask. Recommended yes.
4. **AppOrchestrator without slack_client:** Allow `slack_client=None`. Methods that need Slack will raise. Documented and tested.

---

## Out of scope (call out in README "What's Next")

- Multi-turn / thread memory.
- Postgres / Snowflake adapter (architecture supports the swap via `DatabaseEngineInterface`).
- OpenTelemetry / proper observability beyond log lines.
- Auth on the web UI (anyone with the link can ask questions and burn API budget — note this risk).
- Performance benchmark suite.
- New chart types beyond the existing 9.

---

## Review section (filled in post-execution)

_Empty until work completes._
