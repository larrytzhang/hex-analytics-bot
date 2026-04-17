"""App orchestrator — the central adapter layer.

Implements OrchestratorInterface. This is the ONLY file that knows about
all modules. Wires Brain <-> Viz and translates between their data types.
Two entry points:

* ``compute_answer(question)`` — transport-agnostic. Runs brain → viz
  and returns a plain ``AnswerResult``. Used by the Web UI and by
  ``handle_question`` below.
* ``handle_question(SlackRequest)`` — Slack-specific. Calls
  ``compute_answer`` and then performs Slack delivery (file upload,
  thread reply formatting).

Splitting the pipeline this way keeps brain/viz wiring in one place
while letting any I/O surface reuse it without depending on Slack types.
"""

import asyncio
import logging
import time

from hex.shared.errors import BrainError, VisualizationError
from hex.shared.interfaces import BrainInterface, ChartEngineInterface, OrchestratorInterface
from hex.shared.models import (
    AnswerResult,
    ChartRequest,
    ChartType,
    QueryResult,
    ResponseType,
    SlackRequest,
    SlackResponse,
)

logger = logging.getLogger(__name__)


class AppOrchestrator(OrchestratorInterface):
    """Top-level orchestrator wiring Brain, Viz, and (optionally) Slack.

    Receives BrainInterface and ChartEngineInterface via constructor injection.
    Does NOT receive DatabaseEngineInterface — Brain owns DB access internally.
    The ``slack_client`` is optional so the same orchestrator can serve the
    Slack gateway and the headless web UI from one wiring point.

    Attributes:
        _brain:  BrainInterface for question answering.
        _chart:  ChartEngineInterface for visualization.
        _slack:  Slack AsyncWebClient for file uploads, or None for non-Slack callers.
    """

    def __init__(
        self,
        brain: BrainInterface,
        chart_engine: ChartEngineInterface,
        slack_client=None,
    ) -> None:
        """Initialize the orchestrator with brain, viz, and optional Slack client.

        Args:
            brain:        BrainInterface for processing questions.
            chart_engine: ChartEngineInterface for rendering charts.
            slack_client: Slack AsyncWebClient. Optional — only required if
                          ``handle_question`` is called. The web UI passes None.
        """
        self._brain = brain
        self._chart = chart_engine
        self._slack = slack_client

    # ── Transport-agnostic pipeline ────────────────────────────────────────

    async def compute_answer(
        self,
        question: str,
        brain_override: BrainInterface | None = None,
    ) -> AnswerResult:
        """Run brain → viz once, return plain data with no Slack coupling.

        Catches errors from each stage so the caller never has to. The
        contract is: this method does not raise — failures land in
        ``AnswerResult.error`` with a user-friendly message. That keeps
        web/Slack callers simple and uniform.

        Args:
            question: Plain-English question from the user.

        Returns:
            AnswerResult with text_summary, optional query_result, optional
            chart_bytes, optional error, and total latency in ms.
        """
        started = time.perf_counter()
        # Per-session override if supplied (web upload path); otherwise
        # use the orchestrator's default brain (Slack + sample-data web).
        brain = brain_override or self._brain

        # Stage 1 — Brain. Convert any BrainError into a friendly message.
        try:
            brain_response = await brain.ask(question)
        except BrainError as e:
            elapsed = int((time.perf_counter() - started) * 1000)
            logger.warning("compute_answer brain_error=%s latency_ms=%d", e, elapsed)
            return AnswerResult(
                text_summary="",
                error=f"Something went wrong: {e}",
                latency_ms=elapsed,
            )

        # Stage 2 — Unanswerable. Brain may legitimately return no data
        # (e.g. question outside the schema). Surface the brain's text.
        if brain_response.error or brain_response.query_result is None:
            elapsed = int((time.perf_counter() - started) * 1000)
            return AnswerResult(
                text_summary=brain_response.text_summary
                or "I can't answer that with the available data.",
                error=brain_response.error,
                latency_ms=elapsed,
            )

        # Stage 3 — Chart. Optional and non-fatal. If the LLM said NONE,
        # skip. If viz raises, downgrade to text-only rather than failing
        # the whole answer.
        chart_bytes: bytes | None = None
        if brain_response.suggested_chart != ChartType.NONE:
            try:
                chart_request = self._build_chart_request(
                    brain_response.query_result,
                    brain_response.suggested_chart,
                    title=question,
                )
                # asyncio.to_thread because viz is sync (matplotlib).
                chart_result = await asyncio.to_thread(self._chart.render, chart_request)
                chart_bytes = chart_result.image_bytes
            except VisualizationError as e:
                logger.info("Chart skipped: %s", e)

        elapsed = int((time.perf_counter() - started) * 1000)
        logger.info(
            "compute_answer ok rows=%d chart=%s latency_ms=%d",
            brain_response.query_result.row_count,
            "yes" if chart_bytes else "no",
            elapsed,
        )
        return AnswerResult(
            text_summary=brain_response.text_summary,
            query_result=brain_response.query_result,
            chart_bytes=chart_bytes,
            latency_ms=elapsed,
        )

    # ── Slack-specific adapter ─────────────────────────────────────────────

    async def handle_question(self, request: SlackRequest) -> SlackResponse:
        """Slack adapter over compute_answer: also uploads chart in-thread.

        Args:
            request: Normalized SlackRequest from the gateway.

        Returns:
            SlackResponse ready for the Gateway to send back.
        """
        if self._slack is None:
            # Defensive: handle_question requires a Slack client. If one
            # was never injected, fail loudly rather than silently
            # returning a half-baked response.
            raise RuntimeError(
                "AppOrchestrator.handle_question called without a slack_client; "
                "use compute_answer() for non-Slack callers."
            )

        answer = await self.compute_answer(request.clean_text)

        # Pipeline error → text-only error reply.
        if answer.error and not answer.text_summary:
            return SlackResponse(
                channel_id=request.channel_id,
                thread_ts=request.thread_ts,
                response_type=ResponseType.TEXT,
                text=answer.error,
            )

        # Format text + truncated table.
        text = self._format_text_response(answer.text_summary, answer.query_result)

        # Upload chart in-thread if we have one. Failure is non-fatal.
        if answer.chart_bytes:
            try:
                await self._slack.files_upload_v2(
                    channel=request.channel_id,
                    thread_ts=request.thread_ts,
                    content=answer.chart_bytes,
                    filename="chart.png",
                    title=request.clean_text,
                    alt_text=answer.text_summary,
                )
                return SlackResponse(
                    channel_id=request.channel_id,
                    thread_ts=request.thread_ts,
                    response_type=ResponseType.TEXT_AND_IMAGE,
                    text=text,
                    image_bytes=answer.chart_bytes,
                    alt_text=answer.text_summary,
                )
            except Exception:
                logger.warning("Chart upload failed, degrading to text-only")

        return SlackResponse(
            channel_id=request.channel_id,
            thread_ts=request.thread_ts,
            response_type=ResponseType.TEXT,
            text=text,
        )

    # ── Helpers ────────────────────────────────────────────────────────────

    def _build_chart_request(self, qr: QueryResult, chart_type: ChartType, title: str) -> ChartRequest:
        """Convert QueryResult -> ChartRequest for the Viz module.

        Args:
            qr:         The query result with data to chart.
            chart_type: The suggested chart type from the Brain.
            title:      Chart title string.

        Returns:
            ChartRequest ready for the Viz engine.
        """
        return ChartRequest(data=qr.to_dicts(), chart_type=chart_type, title=title)

    def _format_text_response(self, summary: str, query_result: QueryResult | None) -> str:
        """Format text with optional truncated markdown table (max 10 rows).

        Args:
            summary:      Plain-English answer text.
            query_result: The query result to format (may be None).

        Returns:
            Formatted text string with optional markdown table.
        """
        text = summary
        if query_result and query_result.rows:
            if query_result.row_count > 10:
                text += f"\n\n_Showing top 10 of {query_result.row_count} rows..._"
            text += "\n" + self._markdown_table(query_result.columns, query_result.rows[:10])
        return text

    def _markdown_table(self, columns: list[str], rows: list[tuple]) -> str:
        """Render columns + rows as a markdown table string.

        Args:
            columns: Column header names.
            rows:    Data rows as tuples.

        Returns:
            Markdown-formatted table string.
        """
        header = "| " + " | ".join(columns) + " |"
        separator = "| " + " | ".join("---" for _ in columns) + " |"
        body = "\n".join("| " + " | ".join(str(v) for v in row) + " |" for row in rows)
        return f"{header}\n{separator}\n{body}"
