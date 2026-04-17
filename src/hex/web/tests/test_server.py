"""Tests for the FastAPI web server.

The server is a thin HTTP shell over OrchestratorInterface.compute_answer.
These tests pin down its contract:

* GET /healthz returns 200 (Render uses this).
* GET / returns the static HTML shell.
* POST /api/ask happy path returns text + chart_b64 + table data.
* Empty / oversized / missing question → 422 with a JSON error body.
* compute_answer returning AnswerResult.error → 200 with `error` set
  (the UI handles this; we don't 5xx on application errors).
* compute_answer hanging → server returns a friendly timeout error
  instead of letting the worker pin forever.
"""

from __future__ import annotations

import asyncio
import base64
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from hex.shared.models import AnswerResult, QueryResult
from hex.web.config import WebConfig
from hex.web.server import create_app
from hex.web.session import SessionManager


_CSV_BYTES = b"name,score\nalice,90\nbob,80\n"


def _make_client(
    answer: AnswerResult | None = None,
    hang: bool = False,
    *,
    with_sessions: bool = False,
) -> tuple[TestClient, AsyncMock, SessionManager | None]:
    """Build a TestClient with a mock orchestrator.

    Returns the client, the orchestrator mock (so tests can assert what
    it was called with), and the session manager (or None). Tuple is
    awkward but beats having the tests reach into ``client.app.state``.

    Args:
        answer: AnswerResult to return from compute_answer.
        hang:   If True, compute_answer never resolves (used to test timeout).
        with_sessions: If True, wire up a SessionManager so the upload /
                       session endpoints are reachable.
    """
    orch = AsyncMock()
    if hang:
        async def never_returns(_q: str, brain_override=None) -> AnswerResult:
            await asyncio.sleep(60)
            return AnswerResult()
        orch.compute_answer.side_effect = never_returns
    else:
        orch.compute_answer.return_value = answer or AnswerResult(
            text_summary="There are 42 users.",
            query_result=QueryResult(
                success=True,
                columns=["count"],
                rows=[(42,)],
                row_count=1,
                query="SELECT COUNT(*) FROM users",
            ),
            chart_bytes=None,
            latency_ms=123,
        )
    # Tight timeout so the hang test runs in well under a second.
    cfg = WebConfig(REQUEST_TIMEOUT_SECONDS=1)
    sm: SessionManager | None = None
    if with_sessions:
        sm = SessionManager(lambda _db: MagicMock(name="session_brain"))
    return TestClient(create_app(orch, cfg, session_manager=sm)), orch, sm


def test_healthz_returns_ok():
    """Render hits this endpoint to gate traffic; must always 200."""
    client, _, _ = _make_client()
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_root_serves_html_shell():
    """The single-page UI must be served at /."""
    client, _, _ = _make_client()
    r = client.get("/")
    assert r.status_code == 200
    assert "Hex Analytics Bot" in r.text
    assert "<title>" in r.text


def test_ask_happy_path_returns_text_and_table():
    """Standard answer flow: text + columns + rows; no chart for this case."""
    client, _, _ = _make_client()
    r = client.post("/api/ask", json={"question": "How many users?"})
    assert r.status_code == 200
    body = r.json()
    assert "42" in body["text"]
    assert body["columns"] == ["count"]
    assert body["rows"] == [[42]]
    assert body["row_count"] == 1
    assert body["chart_b64"] is None
    assert body["latency_ms"] == 123
    assert body["error"] is None


def test_ask_returns_chart_b64_when_present():
    """When AnswerResult has chart_bytes, the response carries base64 PNG."""
    raw = b"\x89PNG\r\n\x1a\nfake-image-payload"
    client, _, _ = _make_client(AnswerResult(
        text_summary="Revenue by plan",
        query_result=QueryResult(
            success=True, columns=["plan", "revenue"],
            rows=[("Pro", 200), ("Starter", 100)],
            row_count=2, query="SELECT ...",
        ),
        chart_bytes=raw,
        latency_ms=2500,
    ))
    r = client.post("/api/ask", json={"question": "Revenue by plan?"})
    body = r.json()
    assert body["chart_b64"] == base64.b64encode(raw).decode("ascii")
    assert body["chart_mime"] == "image/png"


def test_ask_rejects_empty_question():
    """Pydantic min_length=1 → 422; we also strip whitespace and reject blank."""
    client, _, _ = _make_client()
    r = client.post("/api/ask", json={"question": ""})
    assert r.status_code == 422


def test_ask_rejects_whitespace_only_question():
    """A string of spaces is empty after .strip(); the server should 422."""
    client, _, _ = _make_client()
    r = client.post("/api/ask", json={"question": "    "})
    assert r.status_code == 422
    assert r.json()["error"] == "question is empty"


def test_ask_rejects_oversized_question():
    """501-char input exceeds max_length=500 and must be rejected before LLM."""
    client, _, _ = _make_client()
    r = client.post("/api/ask", json={"question": "x" * 501})
    assert r.status_code == 422


def test_ask_returns_200_with_error_on_pipeline_failure():
    """An AnswerResult.error must surface as 200 + `error` field, not 5xx."""
    client, _, _ = _make_client(AnswerResult(
        text_summary="",
        error="Something went wrong: brain timed out",
        latency_ms=10,
    ))
    r = client.post("/api/ask", json={"question": "anything"})
    assert r.status_code == 200
    body = r.json()
    assert body["error"] == "Something went wrong: brain timed out"
    assert body["text"] == ""


def test_ask_times_out_when_pipeline_hangs():
    """A hung compute_answer must not pin a worker; client gets a friendly error."""
    client, _, _ = _make_client(hang=True)
    r = client.post("/api/ask", json={"question": "long question"})
    assert r.status_code == 200
    body = r.json()
    assert body["error"] is not None
    assert "longer than" in body["error"].lower()


@pytest.mark.parametrize("payload", [{}, {"q": "missing field name"}])
def test_ask_rejects_malformed_payload(payload):
    """Missing 'question' field must 422 before reaching the orchestrator."""
    client, _, _ = _make_client()
    r = client.post("/api/ask", json=payload)
    assert r.status_code == 422


# ── Upload + session routing ──────────────────────────────────────────────


def test_upload_happy_path_returns_session_metadata():
    """A valid CSV upload returns session_id + schema + preview rows."""
    client, _, _ = _make_client(with_sessions=True)
    r = client.post(
        "/api/upload",
        files={"file": ("scores.csv", _CSV_BYTES, "text/csv")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"]
    assert body["table_name"] == "scores"
    assert body["row_count"] == 2
    names = [c["name"] for c in body["columns"]]
    assert names == ["name", "score"]
    assert len(body["preview_rows"]) == 2


def test_upload_without_session_manager_returns_501():
    """If the server wasn't built with sessions, /api/upload must 501, not crash."""
    client, _, _ = _make_client(with_sessions=False)
    r = client.post(
        "/api/upload",
        files={"file": ("a.csv", _CSV_BYTES, "text/csv")},
    )
    assert r.status_code == 501


def test_upload_rejects_empty_file():
    """An empty upload is a client error; must 422 with a clear message."""
    client, _, _ = _make_client(with_sessions=True)
    r = client.post(
        "/api/upload",
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert r.status_code == 422


def test_upload_rejects_malformed_csv():
    """Malformed CSV raises CSVValidationError inside the loader → 422."""
    client, _, _ = _make_client(with_sessions=True)
    # Header only; no data rows — the loader rejects this.
    r = client.post(
        "/api/upload",
        files={"file": ("hdr.csv", b"a,b,c\n", "text/csv")},
    )
    assert r.status_code == 422
    assert "no data rows" in r.json()["error"].lower()


def test_upload_rejects_oversized_body():
    """Body above MAX_UPLOAD_BYTES → 413 before reaching the loader."""
    # Tight cap so the test stays fast.
    cfg = WebConfig(REQUEST_TIMEOUT_SECONDS=1, MAX_UPLOAD_BYTES=64)
    sm = SessionManager(lambda _db: MagicMock())
    client = TestClient(create_app(AsyncMock(), cfg, session_manager=sm))
    r = client.post(
        "/api/upload",
        files={"file": ("big.csv", b"x" * 256, "text/csv")},
    )
    assert r.status_code == 413


def test_ask_with_session_id_routes_to_session_brain():
    """POST /api/ask with session_id must pass the session's brain as override."""
    client, orch, sm = _make_client(with_sessions=True)
    assert sm is not None
    session = sm.create(_CSV_BYTES, "a.csv")

    r = client.post(
        "/api/ask",
        json={"question": "how many rows?", "session_id": session.session_id},
    )
    assert r.status_code == 200
    # The orchestrator was called with the session's brain as override,
    # not the default brain. Direct identity check — the session brain
    # is a MagicMock we can compare against.
    _, kwargs = orch.compute_answer.call_args
    assert kwargs["brain_override"] is session.brain


def test_ask_with_unknown_session_id_returns_410():
    """Unknown session id → 410 Gone so the UI can prompt for re-upload."""
    client, _, _ = _make_client(with_sessions=True)
    r = client.post(
        "/api/ask",
        json={"question": "anything", "session_id": "does-not-exist"},
    )
    assert r.status_code == 410
    assert "session expired" in r.json()["error"].lower()


def test_ask_without_session_id_uses_default_brain():
    """No session_id → compute_answer called with brain_override=None."""
    client, orch, _ = _make_client(with_sessions=True)
    r = client.post("/api/ask", json={"question": "default path"})
    assert r.status_code == 200
    _, kwargs = orch.compute_answer.call_args
    assert kwargs["brain_override"] is None


def test_ask_with_session_but_no_session_manager_returns_400():
    """Client supplied a session_id but the server has no manager → 400."""
    client, _, _ = _make_client(with_sessions=False)
    r = client.post(
        "/api/ask",
        json={"question": "anything", "session_id": "abc"},
    )
    assert r.status_code == 400


def test_get_session_returns_metadata():
    """GET /api/session/{id} returns the same payload as upload."""
    client, _, sm = _make_client(with_sessions=True)
    assert sm is not None
    session = sm.create(_CSV_BYTES, "a.csv")
    r = client.get(f"/api/session/{session.session_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == session.session_id
    assert body["table_name"] == "a"


def test_get_session_404_for_unknown_id():
    """Unknown id on GET /api/session/{id} → 404 (not 410)."""
    client, _, _ = _make_client(with_sessions=True)
    r = client.get("/api/session/does-not-exist")
    assert r.status_code == 404


def test_delete_session_removes_it():
    """DELETE is 204, and the session is unreachable afterwards."""
    client, _, sm = _make_client(with_sessions=True)
    assert sm is not None
    session = sm.create(_CSV_BYTES, "a.csv")
    r = client.delete(f"/api/session/{session.session_id}")
    assert r.status_code == 204
    # A subsequent ask with that id now 410s.
    r = client.post(
        "/api/ask",
        json={"question": "anything", "session_id": session.session_id},
    )
    assert r.status_code == 410


def test_delete_unknown_session_returns_404():
    """Deleting a session that never existed → 404."""
    client, _, _ = _make_client(with_sessions=True)
    r = client.delete("/api/session/does-not-exist")
    assert r.status_code == 404
