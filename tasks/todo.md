# Hex Bot — CSV Upload + Per-Session Isolation

**Goal:** Let reviewers upload their own CSV and ask questions against it. Each browser session gets its own isolated in-memory database so two people clicking through the demo at the same time don't see each other's data.

**Scope:** Option B from the design discussion — per-session isolation. Real data path only for the web UI; Slack stays on the mock dataset.

**Estimated effort:** ~5–6 hours of careful work, ~8 atomic commits.

---

## Architectural decisions (locked before start)

1. **Brain-per-session, not DB param threading.** The upload creates a new `SQLiteEngine` + a new `BrainOrchestrator` pointing at it. `AppOrchestrator.compute_answer` gains a single optional `brain_override` parameter — Slack passes nothing (uses the mock brain injected at startup), Web passes the session's brain. One viz engine is shared (stateless).
2. **SessionManager lives in `web/`.** Session storage is web-specific state. Keying: server-minted UUID returned in the upload response, stored by the frontend in `localStorage` and echoed in each `/api/ask`.
3. **In-memory only.** Render free-tier disk is ephemeral anyway; no persistence needed for a demo. 30-min inactivity TTL, max 20 concurrent sessions, LRU eviction when full.
4. **Upload limits:** 5 MB file, 10,000 rows, 50 columns. Enforced in the CSV loader; the HTTP layer caps the body size too.
5. **Semantic glossary off for uploaded data.** The SaaS glossary (MRR, ARR, churn) is wrong for arbitrary CSVs. `BrainOrchestrator(use_glossary=False)` for session brains.
6. **API surface additions (not replacements):**
   - `POST /api/upload` (multipart) → `{session_id, table_name, schema, row_count}`
   - `POST /api/ask` body gains optional `session_id` — absent = mock dataset, present = that session's data
   - `DELETE /api/session/{session_id}` — explicit cleanup (frontend "Start over" button)

---

## Phase 1 — DB: loadable SQLiteEngine + CSV parser (1 hr)

The current `SQLiteEngine.__init__` unconditionally seeds mock data. Split that so we can construct a blank engine, then load a CSV into it.

### Files

- `src/hex/db/engine.py` — change signature to `__init__(self, *, seed: bool = True)`. Blank path still creates `_meta` row after loading so `health_check()` works.
- `src/hex/db/csv_loader.py` (new) — pure CSV → SQLite loader with no IO, no LLM, no framework:
  - `load_csv_into(conn, csv_bytes: bytes, filename_hint: str) -> LoadedTable`
  - `sanitize_identifier(raw: str) -> str` — lowercase, non-alphanumeric → `_`, collapse dupes, strip edges, prefix `col_` if digit-leading
  - `infer_column_types(sample_rows) -> list[str]` — INTEGER / REAL / TEXT
  - Enforces 5 MB / 10k row / 50 col caps; raises `CSVValidationError` with a user-friendly message
  - Returns `LoadedTable(table_name, columns=[{name, type}], row_count)`
- `src/hex/shared/models.py` — add `LoadedTable` dataclass
- `src/hex/shared/errors.py` — add `CSVValidationError(HexError)`

### Tests — `src/hex/db/tests/test_csv_loader.py`

- happy path: 3-col CSV loads, types inferred correctly
- column name sanitization (`"First Name"` → `first_name`, `"2023"` → `col_2023`, duplicates dedup’d)
- table name derived from filename, fallback to `data`
- type inference across mixed-int-with-nulls, floats, dates-as-text
- oversized file (>5MB) raises `CSVValidationError`
- too-many-rows (>10k) raises with clear message
- too-many-cols (>50) raises
- malformed CSV (unclosed quote) raises `CSVValidationError` not generic crash
- non-UTF8 encoding (latin-1) handled or rejected cleanly
- empty CSV raises
- single-row CSV (header only, no data) raises

### Commit

`feat(db): blank-init SQLiteEngine + CSV loader with validation`

---

## Phase 2 — Brain: opt-out of the SaaS glossary (20 min)

The brain's semantic enrichment injects a SaaS glossary that's wrong for user data. Add a flag.

### Files

- `src/hex/brain/orchestrator.py` — `BrainOrchestrator.__init__` gains `use_glossary: bool = True`. When `False`, pass empty dict to `enrich()` or skip the glossary section of the prompt.
- `src/hex/brain/semantic_layer.py` — inspect: if the function unconditionally injects the glossary, change to accept a flag or let the orchestrator skip the glossary prompt segment. Minimize surface area — prefer the orchestrator-side skip over mutating the enricher.
- `src/hex/brain/tests/test_orchestrator.py` — one test: `use_glossary=False` → system prompt does not contain the glossary header.

### Commit

`feat(brain): use_glossary flag for user-uploaded schemas`

---

## Phase 3 — Orchestrator seam: brain override on compute_answer (20 min)

Thread a single optional parameter through so the web layer can route a request to a session brain.

### Files

- `src/hex/shared/interfaces.py` — `OrchestratorInterface.compute_answer(question, brain_override: BrainInterface | None = None)`
- `src/hex/app/orchestrator.py` — accept the override; resolve with `brain = brain_override or self._brain`; everything else unchanged.
- `src/hex/tests/test_compute_answer.py` — add one test: pass a stub brain override; verify it's called instead of `self._brain`.

### Commit

`refactor(app): compute_answer accepts optional brain_override`

---

## Phase 4 — Session manager (1 hr)

The heart of isolation. Owns session_id → DatasetSession lifecycle with TTL + LRU.

### Files

- `src/hex/web/session.py` (new):
  - `DatasetSession` dataclass: `session_id`, `created_at`, `last_used_at`, `db: SQLiteEngine`, `brain: BrainInterface`, `table_name`, `schema`, `row_count`
  - `SessionManager`:
    - `__init__(self, brain_factory, *, max_sessions=20, ttl_seconds=1800)`
    - `create(loaded_table) -> DatasetSession` — builds DB, builds brain via `brain_factory(db)`, assigns UUID, stores, evicts if over cap
    - `get(session_id) -> DatasetSession | None` — refreshes `last_used_at`; evicts expired lazily on access
    - `delete(session_id) -> None` — explicit cleanup
    - `_evict_expired()` / `_evict_lru()` — private, run on every create/get
  - `brain_factory` is a callable `(db: DatabaseEngineInterface) -> BrainInterface` — inverted dependency so `SessionManager` has no imports from `brain/`. Web wiring composes it.

### Tests — `src/hex/web/tests/test_session.py`

- create returns a session with unique UUID
- get returns the same session if not expired; returns None if never created
- get refreshes `last_used_at`
- expired session (past TTL) returns None on next get AND is removed from internal map
- when at max_sessions, creating a new one evicts the LRU
- delete removes the session
- two parallel sessions have independent DBs (write to one, other unchanged — use raw SQL since our engine is read-only, or assert schema isolation)

### Commit

`feat(web): SessionManager with TTL + LRU eviction`

---

## Phase 5 — Web endpoints (1 hr)

Add the three endpoints, wire session manager into `create_app`.

### Files

- `src/hex/web/config.py` — add `MAX_UPLOAD_BYTES = 5 * 1024 * 1024`, `SESSION_TTL_SECONDS = 1800`, `MAX_SESSIONS = 20`.
- `src/hex/web/server.py`:
  - `create_app(orchestrator, *, brain_factory, session_manager=None)` — construct a default `SessionManager` if none supplied.
  - `POST /api/upload` — multipart `file` field. Body size guard (413 if over cap). Call `load_csv_into`, then `session_manager.create(loaded_table)`. Return `{session_id, table_name, schema: [{name, type}], row_count, preview_rows: list[dict]}` (first 5 rows for UI preview).
  - `POST /api/ask` — body gains optional `session_id`. If present → resolve session → pass `session.brain` as `brain_override`. If session expired/missing → 410 Gone with a clear message.
  - `DELETE /api/session/{session_id}` — 204 on success, 404 if not found.
  - `GET /api/session/{session_id}` — read session metadata (table_name, schema, row_count); 404 if not found. Powers frontend state restore after reload.
- `web_main.py` — define `def build_brain(db): return BrainOrchestrator(brain_config, db, llm_client, use_glossary=False)` and pass as `brain_factory` into `create_app`.

### Tests — `src/hex/web/tests/test_server.py` (add to existing)

- `POST /api/upload` happy path → 200 with session_id + schema
- upload with oversized file → 413
- upload with malformed CSV → 422 with `CSVValidationError` message
- `POST /api/ask` with valid session_id → routes to session brain (mock brain_factory asserts)
- `POST /api/ask` with unknown session_id → 410
- `POST /api/ask` with no session_id → uses default brain (mock data)
- `DELETE /api/session/{id}` → 204; subsequent ask with same id → 410
- `GET /api/session/{id}` → 200 with metadata; unknown → 404
- isolation integration: upload session A, upload session B, ask against A, verify B's data not referenced

### Commit

`feat(web): /api/upload, session-scoped /api/ask, session delete/get`

---

## Phase 6 — Frontend (1 hr)

Upload UX in the single-page HTML. No build step, vanilla JS + Tailwind CDN.

### Files

- `src/hex/web/static/index.html`:
  - Data source toggle at the top: "Sample dataset" (default, current pills visible) vs "Upload my own CSV"
  - When "Upload" selected:
    - drag-drop file zone + file input
    - uploading spinner
    - on success: show uploaded table name + schema preview (columns with types)
    - sample question pills hidden (they reference mock schema)
    - input placeholder changes to "Ask about your uploaded data..."
    - "Start over" button: DELETE session, clear localStorage, revert to sample mode
  - `session_id` stored in `localStorage.hex_session_id`; restored on load via `GET /api/session/{id}` (swallows 404 as "expired, go back to sample mode")
  - `/api/ask` always sends `session_id` if present in localStorage

### Manual browser verification (no automated test for the HTML)

- upload a sample CSV, ask a question against it, get an answer
- reload mid-session → state restored
- "Start over" → back to sample mode
- expired session (manually clear server map or wait) → graceful fallback

### Commit

`feat(web): upload UI, schema preview, session restore`

---

## Phase 7 — Docs + deploy verification (30 min)

### Files

- `README.md`:
  - New "Try with your own data" paragraph under the quickstart
  - Mention session isolation + 5 MB / 10k row caps
  - "What's Next" — update: real warehouse adapter still open, but user-upload is now shipped.
- `src/hex/web/tests/conftest.py` / any shared fixture updates for tests.
- Run full `uv run pytest src/hex` — verify the existing 137 pass + all new tests pass.
- Local browser smoke test via `uv run python web_main.py`:
  - Sample mode: click each pill, all answer correctly
  - Upload a small CSV, ask a question, verify answer references uploaded columns
- Commit: `docs: README — user upload path + session isolation`
- Push; Render auto-deploy; verify live URL works end-to-end.

---

## Phase 8 — Post-execution review

Fill in after shipping:

- What changed vs plan (deviations, surprises)
- Architectural calls worth flagging
- Known follow-ups

---

## Open risk (documented, accepted for MVP)

- **Memory pressure on Render free tier (512 MB).** 20 sessions × 5 MB = 100 MB worst case + matplotlib overhead. Acceptable; eviction handles the long tail. If we see OOM kills, lower `MAX_SESSIONS` first.
- **Unauthenticated upload endpoint.** Anyone with the link can upload a 5 MB file up to 20× concurrent. Rate-limiting is out of scope; the Anthropic spend cap + Render's own request throttling are the real protection. Flagged in README.
- **No CSV schema-change-after-upload.** A session's table is fixed. To change data, user clicks "Start over" → new session. Documented in UI.
