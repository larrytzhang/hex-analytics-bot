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
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from hex.shared.models import AnswerResult, QueryResult
from hex.web.config import WebConfig
from hex.web.server import create_app


def _make_client(answer: AnswerResult | None = None, hang: bool = False) -> TestClient:
    """Build a TestClient with a mock orchestrator.

    Args:
        answer: AnswerResult to return from compute_answer.
        hang:   If True, compute_answer never resolves (used to test timeout).
    """
    orch = AsyncMock()
    if hang:
        async def never_returns(_q: str) -> AnswerResult:
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
    return TestClient(create_app(orch, cfg))


def test_healthz_returns_ok():
    """Render hits this endpoint to gate traffic; must always 200."""
    client = _make_client()
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_root_serves_html_shell():
    """The single-page UI must be served at /."""
    client = _make_client()
    r = client.get("/")
    assert r.status_code == 200
    assert "Hex Analytics Bot" in r.text
    assert "<title>" in r.text


def test_ask_happy_path_returns_text_and_table():
    """Standard answer flow: text + columns + rows; no chart for this case."""
    client = _make_client()
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
    client = _make_client(AnswerResult(
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
    client = _make_client()
    r = client.post("/api/ask", json={"question": ""})
    assert r.status_code == 422


def test_ask_rejects_whitespace_only_question():
    """A string of spaces is empty after .strip(); the server should 422."""
    client = _make_client()
    r = client.post("/api/ask", json={"question": "    "})
    assert r.status_code == 422
    assert r.json()["error"] == "question is empty"


def test_ask_rejects_oversized_question():
    """501-char input exceeds max_length=500 and must be rejected before LLM."""
    client = _make_client()
    r = client.post("/api/ask", json={"question": "x" * 501})
    assert r.status_code == 422


def test_ask_returns_200_with_error_on_pipeline_failure():
    """An AnswerResult.error must surface as 200 + `error` field, not 5xx."""
    client = _make_client(AnswerResult(
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
    client = _make_client(hang=True)
    r = client.post("/api/ask", json={"question": "long question"})
    assert r.status_code == 200
    body = r.json()
    assert body["error"] is not None
    assert "longer than" in body["error"].lower()


@pytest.mark.parametrize("payload", [{}, {"q": "missing field name"}])
def test_ask_rejects_malformed_payload(payload):
    """Missing 'question' field must 422 before reaching the orchestrator."""
    client = _make_client()
    r = client.post("/api/ask", json=payload)
    assert r.status_code == 422
