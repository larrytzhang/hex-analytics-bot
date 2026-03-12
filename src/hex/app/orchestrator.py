"""App orchestrator — the central adapter layer.

Implements OrchestratorInterface. This is the ONLY file that knows about
all modules. Wires Gateway <-> Brain <-> Viz and translates between their
data types. Does NOT receive db_engine — Brain owns DB access.
"""

import asyncio
import logging

from hex.shared.errors import BrainError, VisualizationError
from hex.shared.interfaces import BrainInterface, ChartEngineInterface, OrchestratorInterface
from hex.shared.models import (
    ChartRequest,
    ChartType,
    QueryResult,
    ResponseType,
    SlackRequest,
    SlackResponse,
)

logger = logging.getLogger(__name__)


class AppOrchestrator(OrchestratorInterface):
    """Top-level orchestrator wiring Brain, Viz, and Slack together.

    Receives BrainInterface and ChartEngineInterface via constructor injection.
    Does NOT receive DatabaseEngineInterface — Brain owns DB access internally.

    Attributes:
        _brain:  BrainInterface for question answering.
        _chart:  ChartEngineInterface for visualization.
        _slack:  Slack AsyncWebClient for file uploads.
    """

    def __init__(self, brain: BrainInterface, chart_engine: ChartEngineInterface, slack_client) -> None:
        """Initialize the orchestrator with all dependencies.

        Args:
            brain:        BrainInterface for processing questions.
            chart_engine: ChartEngineInterface for rendering charts.
            slack_client: Slack AsyncWebClient for files_upload_v2.
        """
        self._brain = brain
        self._chart = chart_engine
        self._slack = slack_client

    async def handle_question(self, request: SlackRequest) -> SlackResponse:
        """Full pipeline: SlackRequest -> Brain -> Viz -> SlackResponse.

        Args:
            request: Normalized SlackRequest from the gateway.

        Returns:
            SlackResponse ready to be sent back to Slack.
        """
        question = request.clean_text

        # Step 1: Call Brain
        try:
            brain_response = await self._brain.ask(question)
        except BrainError as e:
            return self._error_response(request, str(e))

        # Step 2: Handle unanswerable questions
        if brain_response.error or brain_response.query_result is None:
            return SlackResponse(
                channel_id=request.channel_id,
                thread_ts=request.thread_ts,
                text=brain_response.text_summary or "I can't answer that with the available data.",
            )

        # Step 3: Generate chart (if suggested)
        chart_bytes = None
        alt_text = ""
        if brain_response.suggested_chart != ChartType.NONE:
            try:
                chart_request = self._build_chart_request(
                    brain_response.query_result,
                    brain_response.suggested_chart,
                    title=question,
                )
                # Wrap sync Viz call in async
                chart_result = await asyncio.to_thread(self._chart.render, chart_request)
                chart_bytes = chart_result.image_bytes
                alt_text = brain_response.text_summary
            except VisualizationError:
                pass  # Chart failure is non-fatal

        # Step 4: Build text (truncate large results)
        text = self._format_text_response(brain_response.text_summary, brain_response.query_result)

        # Step 5: Upload chart to Slack if we have one
        if chart_bytes:
            try:
                await self._slack.files_upload_v2(
                    channel=request.channel_id,
                    thread_ts=request.thread_ts,
                    content=chart_bytes,
                    filename="chart.png",
                    title=question,
                    alt_text=alt_text,
                )
            except Exception:
                chart_bytes = None  # Degrade to text-only
                logger.warning("Chart upload failed, degrading to text-only")

            return SlackResponse(
                channel_id=request.channel_id,
                thread_ts=request.thread_ts,
                response_type=ResponseType.TEXT_AND_IMAGE,
                text=text,
                image_bytes=chart_bytes,
                alt_text=alt_text,
            )

        # Step 6: Text-only response
        return SlackResponse(
            channel_id=request.channel_id,
            thread_ts=request.thread_ts,
            response_type=ResponseType.TEXT,
            text=text,
        )

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

    def _format_text_response(self, summary: str, query_result: QueryResult) -> str:
        """Format text with optional truncated table (max 10 rows).

        Args:
            summary:      Plain-English answer text.
            query_result: The query result to format.

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

    def _error_response(self, request: SlackRequest, message: str) -> SlackResponse:
        """Build a user-friendly error SlackResponse.

        Args:
            request: The original SlackRequest for channel/thread info.
            message: Error message to display.

        Returns:
            SlackResponse with error text.
        """
        return SlackResponse(
            channel_id=request.channel_id,
            thread_ts=request.thread_ts,
            response_type=ResponseType.TEXT,
            text=f"Something went wrong: {message}",
        )
