"""FastAPI server for the web demo.

Exposes three endpoints:

* ``GET /`` serves the single-page chat UI from ``static/index.html``.
* ``GET /healthz`` returns 200 — used by Render for health checks.
* ``POST /api/ask`` takes ``{question}``, calls
  ``orchestrator.compute_answer``, and returns text + chart bytes
  (base64) as JSON.

The server is intentionally tiny. All real work lives in the
AppOrchestrator; we just translate HTTP ↔ AnswerResult and apply
guardrails (timeout, length cap, base64 chart encoding).
"""

from __future__ import annotations

import asyncio
import base64
import logging
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from hex.shared.errors import CSVValidationError
from hex.shared.interfaces import OrchestratorInterface
from hex.web.config import WebConfig
from hex.web.session import SessionManager

logger = logging.getLogger(__name__)

# Static assets ship inside the package so deploys don't need extra paths.
_STATIC_DIR = Path(__file__).parent / "static"


class AskRequest(BaseModel):
    """Request body for POST /api/ask.

    Pydantic does length and type validation for free; oversized or
    empty inputs return a 422 before they ever hit the brain.
    """

    question: str = Field(..., min_length=1, max_length=500)
    # Optional: when present, routes the question to the uploaded-CSV
    # session's DB. Absent = default (sample) dataset.
    session_id: str | None = None


class AskResponse(BaseModel):
    """Response body for POST /api/ask.

    Attributes:
        text:       Plain-English answer (may include a markdown table).
        columns:    Result column names, useful for client-side rendering.
        rows:       Result rows as lists; capped at 50 to bound payload size.
        row_count:  Total rows produced by the SQL (may exceed len(rows)).
        chart_b64:  Base64-encoded PNG of the chart, or None.
        chart_mime: MIME type for chart_b64 (always image/png today).
        latency_ms: Total brain → viz pipeline time, surfaced for transparency.
        error:      User-facing error message; non-null means the pipeline
                    failed in a way the user should see.
    """

    text: str
    columns: list[str] = []
    rows: list[list] = []
    row_count: int = 0
    chart_b64: str | None = None
    chart_mime: str = "image/png"
    latency_ms: int = 0
    error: str | None = None


def create_app(
    orchestrator: OrchestratorInterface,
    config: WebConfig | None = None,
    session_manager: SessionManager | None = None,
) -> FastAPI:
    """Build a FastAPI app wired to the given orchestrator.

    Factory pattern (rather than a module-level app) so tests can inject a
    mock orchestrator without monkey-patching globals, and so production
    can wire DB → Brain → Viz once and pass a single AppOrchestrator in.

    Args:
        orchestrator: Anything implementing OrchestratorInterface.
                      Only ``compute_answer`` is called.
        config:       WebConfig. Defaults are usually fine.

    Returns:
        Configured FastAPI app.
    """
    cfg = config or WebConfig()
    app = FastAPI(title="Hex Analytics Bot — Demo", version="0.1.0")

    # Mount static assets at /static so the index.html can pull in CSS/JS
    # by relative path. Index page itself is served from "/" explicitly
    # for a cleaner root URL.
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    async def root() -> FileResponse:
        """Serve the single-page UI."""
        return FileResponse(_STATIC_DIR / "index.html")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        """Liveness probe used by Render and similar hosts."""
        return {"status": "ok"}

    @app.post("/api/ask", response_model=AskResponse)
    async def ask(payload: AskRequest) -> AskResponse:
        """Run one question through the brain → viz pipeline.

        Wraps compute_answer in asyncio.wait_for so a hung LLM call can't
        pin a worker forever. Returns 200 with ``error`` set on pipeline
        failures (rather than 5xx) so the UI can render a friendly
        message without distinguishing transport vs. application errors.
        """
        # Strip whitespace defensively; pydantic only validates length, not
        # whether the trimmed string is empty.
        question = payload.question.strip()
        if not question:
            raise HTTPException(status_code=422, detail="question is empty")

        # Resolve per-session brain if a session_id was provided. 410 Gone
        # is the right signal for "your session expired / was evicted" —
        # distinguishable from 404 on the session endpoint so the UI can
        # differentiate "never existed" vs "timed out."
        brain_override = None
        if payload.session_id:
            if session_manager is None:
                raise HTTPException(status_code=400, detail="upload not configured on this server")
            session = session_manager.get(payload.session_id)
            if session is None:
                raise HTTPException(status_code=410, detail="session expired — upload again")
            brain_override = session.brain

        try:
            answer = await asyncio.wait_for(
                orchestrator.compute_answer(question, brain_override=brain_override),
                timeout=cfg.REQUEST_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning("compute_answer timeout question=%r", question[:80])
            return AskResponse(
                text="",
                error=(
                    f"Question took longer than {cfg.REQUEST_TIMEOUT_SECONDS}s. "
                    "Try a simpler question."
                ),
            )

        # Convert the AnswerResult into the wire shape. Chart bytes go to
        # base64 so the JSON payload is self-contained and the browser can
        # render with `<img src="data:image/png;base64,...">`.
        chart_b64: str | None = None
        if answer.chart_bytes:
            chart_b64 = base64.b64encode(answer.chart_bytes).decode("ascii")

        columns: list[str] = []
        rows: list[list] = []
        row_count = 0
        if answer.query_result is not None:
            columns = list(answer.query_result.columns)
            row_count = answer.query_result.row_count
            # Cap rows to keep the payload bounded; UI shows top-N anyway.
            rows = [list(r) for r in answer.query_result.rows[:50]]

        return AskResponse(
            text=answer.text_summary,
            columns=columns,
            rows=rows,
            row_count=row_count,
            chart_b64=chart_b64,
            chart_mime=answer.chart_mime,
            latency_ms=answer.latency_ms,
            error=answer.error,
        )

    @app.post("/api/upload")
    async def upload(file: UploadFile = File(...)) -> dict:
        """Accept a CSV, build a session, return its id + schema preview.

        Size cap is enforced twice: once at the HTTP layer (fast reject of
        a firehose), once inside the CSV loader (authoritative number). We
        stream the body up to MAX_UPLOAD_BYTES + 1 so an oversize payload
        gets a 413 before we allocate the full buffer.
        """
        if session_manager is None:
            raise HTTPException(
                status_code=501,
                detail="uploads are not enabled on this server",
            )

        # Enforce size guard before reading the whole body. FastAPI gives
        # us a spooled temp file, but .read() without a cap still loads
        # everything into memory — so we read-with-limit instead.
        body = await file.read(cfg.MAX_UPLOAD_BYTES + 1)
        if len(body) > cfg.MAX_UPLOAD_BYTES:
            mb = cfg.MAX_UPLOAD_BYTES // (1024 * 1024)
            raise HTTPException(
                status_code=413,
                detail=f"file too large — max {mb} MB",
            )
        if not body:
            raise HTTPException(status_code=422, detail="uploaded file is empty")

        filename = file.filename or "upload.csv"

        # CSV parse + session creation both sit behind a single try so the
        # validation error path is uniform. Any CSVValidationError means
        # the file is unusable — 422 with the loader's user-facing message.
        try:
            session = session_manager.create(body, filename)
        except CSVValidationError as e:
            raise HTTPException(status_code=422, detail=str(e))

        return {
            "session_id": session.session_id,
            "table_name": session.loaded_table.table_name,
            "columns": session.loaded_table.columns,
            "row_count": session.loaded_table.row_count,
            "preview_rows": session.loaded_table.preview_rows,
        }

    @app.get("/api/session/{session_id}")
    async def get_session(session_id: str) -> dict:
        """Return metadata for an existing session, or 404 if gone.

        Powers the frontend's reload-restore path: the UI stashes the id
        in localStorage, and on page load calls this to decide whether
        to repaint the "uploaded data" mode or fall back to the sample
        dataset. 404 (not 410) here because this endpoint is a pure
        lookup — a missing id is indistinguishable from an expired one
        from the client's perspective, and treating them the same
        simplifies the UI.
        """
        if session_manager is None:
            raise HTTPException(status_code=501, detail="uploads are not enabled")
        session = session_manager.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        return {
            "session_id": session.session_id,
            "table_name": session.loaded_table.table_name,
            "columns": session.loaded_table.columns,
            "row_count": session.loaded_table.row_count,
            "preview_rows": session.loaded_table.preview_rows,
        }

    @app.delete("/api/session/{session_id}", status_code=204)
    async def delete_session(session_id: str) -> None:
        """Drop a session explicitly (the UI's 'Start over' button).

        Idempotent-ish: deleting an unknown id returns 404 so the UI can
        surface "already gone" distinctly if it ever matters. 204 on
        success — standard no-body DELETE response.
        """
        if session_manager is None:
            raise HTTPException(status_code=501, detail="uploads are not enabled")
        if not session_manager.delete(session_id):
            raise HTTPException(status_code=404, detail="session not found")
        return None

    @app.exception_handler(HTTPException)
    async def http_error_handler(_request, exc: HTTPException) -> JSONResponse:
        """Uniform JSON shape for HTTP errors so the UI has one parser."""
        return JSONResponse(
            status_code=exc.status_code,
            content={"text": "", "error": exc.detail},
        )

    return app
