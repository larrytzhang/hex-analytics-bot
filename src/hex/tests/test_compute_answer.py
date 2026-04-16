"""Unit tests for AppOrchestrator.compute_answer().

compute_answer() is the transport-agnostic seam that lets both the Slack
gateway and the Web UI share one brain → viz pipeline. These tests pin
down its contract:

* It returns an AnswerResult and never raises.
* BrainError → AnswerResult.error is set, no crash.
* VisualizationError → text returned, chart_bytes is None (graceful).
* Brain returns suggested_chart=NONE → no chart attempted.
* Latency is always measured and >= 0.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from hex.app.orchestrator import AppOrchestrator
from hex.shared.errors import BrainError, EmptyDataError
from hex.shared.models import (
    AnswerResult,
    BrainResponse,
    ChartResult,
    ChartType,
    QueryResult,
)


def _brain_returning(brain_response: BrainResponse) -> AsyncMock:
    """Build an AsyncMock BrainInterface with a fixed response."""
    brain = AsyncMock()
    brain.ask.return_value = brain_response
    return brain


def _chart_returning_png() -> MagicMock:
    """Build a MagicMock ChartEngine that always returns a fake PNG."""
    chart = MagicMock()
    chart.render.return_value = ChartResult(
        image_bytes=b"\x89PNG_fake_bytes",
        chart_type=ChartType.BAR,
    )
    return chart


@pytest.mark.asyncio
async def test_compute_answer_success_with_chart():
    """Happy path: brain returns data + chart suggestion → text + chart bytes."""
    brain = _brain_returning(BrainResponse(
        text_summary="Revenue by plan: Pro=200, Starter=100",
        sql_used="SELECT ...",
        query_result=QueryResult(
            success=True,
            columns=["plan", "revenue"],
            rows=[("Pro", 200), ("Starter", 100)],
            row_count=2,
            query="SELECT ...",
        ),
        suggested_chart=ChartType.BAR,
    ))
    chart = _chart_returning_png()
    orch = AppOrchestrator(brain, chart, slack_client=None)

    answer = await orch.compute_answer("Revenue by plan?")

    assert isinstance(answer, AnswerResult)
    assert "Revenue" in answer.text_summary
    assert answer.query_result is not None
    assert answer.query_result.row_count == 2
    assert answer.chart_bytes == b"\x89PNG_fake_bytes"
    assert answer.chart_mime == "image/png"
    assert answer.error is None
    assert answer.latency_ms >= 0
    chart.render.assert_called_once()


@pytest.mark.asyncio
async def test_compute_answer_brain_error_returns_friendly_error():
    """BrainError → no raise; error message in AnswerResult.error."""
    brain = AsyncMock()
    brain.ask.side_effect = BrainError("LLM is down")
    chart = _chart_returning_png()
    orch = AppOrchestrator(brain, chart, slack_client=None)

    answer = await orch.compute_answer("anything")

    assert answer.error is not None
    assert "went wrong" in answer.error.lower()
    assert "LLM is down" in answer.error
    assert answer.text_summary == ""
    assert answer.chart_bytes is None
    chart.render.assert_not_called()


@pytest.mark.asyncio
async def test_compute_answer_viz_error_degrades_to_text_only():
    """VisualizationError → text + query_result returned, chart_bytes is None."""
    brain = _brain_returning(BrainResponse(
        text_summary="Here is your data",
        sql_used="SELECT ...",
        query_result=QueryResult(
            success=True,
            columns=["x"],
            rows=[(1,)],
            row_count=1,
            query="SELECT ...",
        ),
        suggested_chart=ChartType.BAR,
    ))
    chart = MagicMock()
    chart.render.side_effect = EmptyDataError("no plottable rows")
    orch = AppOrchestrator(brain, chart, slack_client=None)

    answer = await orch.compute_answer("Plot something")

    assert answer.text_summary == "Here is your data"
    assert answer.query_result is not None
    assert answer.chart_bytes is None
    assert answer.error is None  # Viz failure is non-fatal


@pytest.mark.asyncio
async def test_compute_answer_no_chart_suggested_skips_viz():
    """Brain says NONE → viz is never called; text-only answer."""
    brain = _brain_returning(BrainResponse(
        text_summary="There are 42 users.",
        sql_used="SELECT COUNT(*) FROM users",
        query_result=QueryResult(
            success=True,
            columns=["count"],
            rows=[(42,)],
            row_count=1,
            query="SELECT COUNT(*) FROM users",
        ),
        suggested_chart=ChartType.NONE,
    ))
    chart = _chart_returning_png()
    orch = AppOrchestrator(brain, chart, slack_client=None)

    answer = await orch.compute_answer("How many users?")

    assert "42" in answer.text_summary
    assert answer.chart_bytes is None
    chart.render.assert_not_called()


@pytest.mark.asyncio
async def test_compute_answer_unanswerable_question():
    """Brain returns query_result=None → text-only fallback explanation."""
    brain = _brain_returning(BrainResponse(
        text_summary="I can't answer that with the available data.",
        sql_used="",
        query_result=None,
        suggested_chart=ChartType.NONE,
    ))
    chart = _chart_returning_png()
    orch = AppOrchestrator(brain, chart, slack_client=None)

    answer = await orch.compute_answer("What's the weather?")

    assert "can't answer" in answer.text_summary.lower()
    assert answer.query_result is None
    assert answer.chart_bytes is None
    chart.render.assert_not_called()


@pytest.mark.asyncio
async def test_handle_question_without_slack_client_raises():
    """handle_question requires a Slack client; missing one is a wiring bug."""
    brain = _brain_returning(BrainResponse(
        text_summary="ok",
        sql_used="",
        query_result=None,
        suggested_chart=ChartType.NONE,
    ))
    chart = _chart_returning_png()
    orch = AppOrchestrator(brain, chart, slack_client=None)

    from hex.shared.models import SlackRequest

    request = SlackRequest(
        event_id="E", team_id="T", channel_id="C",
        thread_ts="1.0", message_ts="1.0",
        user_id="U", raw_text="<@bot> hi", clean_text="hi",
    )
    with pytest.raises(RuntimeError, match="slack_client"):
        await orch.handle_question(request)
