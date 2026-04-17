"""Abstract base classes (contracts) for all module boundaries.

Every module implements one of these interfaces. Cross-module communication
happens exclusively through these contracts — never through internal
implementation files.
"""

from abc import ABC, abstractmethod

from hex.shared.models import (
    AnswerResult,
    BrainResponse,
    ChartRequest,
    ChartResult,
    ChartType,
    QueryResult,
    SlackRequest,
    SlackResponse,
)


# ── DATABASE ENGINE INTERFACE ──


class DatabaseEngineInterface(ABC):
    """Contract for the Database Execution Engine.

    Consumed by: Brain module (injected at construction).
    Brain wraps all calls in asyncio.to_thread() since this is synchronous.
    """

    @abstractmethod
    def execute_readonly(self, sql: str) -> QueryResult:
        """Execute a read-only SQL query. Rejects INSERT/UPDATE/DELETE/DROP.

        Args:
            sql: The SQL query string to execute.

        Returns:
            QueryResult with success=True and data, or success=False
            with error message.

        Raises:
            ForbiddenQueryError: SQL attempts a write operation.
            QuerySyntaxError:   SQL is malformed.
            QueryExecutionError: Runtime error (bad column, etc.).
        """
        ...

    @abstractmethod
    def get_schema_description(self) -> dict[str, list[dict[str, str]]]:
        """Return raw schema as dict of table -> columns.

        Brain's semantic_layer.py enriches this into SemanticContext.

        Returns:
            Dict mapping table names to lists of column info dicts,
            each containing 'name' and 'type' keys.
        """
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the database is alive and seeded.

        Returns:
            True if a simple query succeeds, False otherwise.
        """
        ...


# ── BRAIN INTERFACE ──


class BrainInterface(ABC):
    """Contract for the Agentic Brain.

    Consumed by: app/orchestrator.py.
    """

    @abstractmethod
    async def ask(self, question: str) -> BrainResponse:
        """Accept a plain-English question, return structured answer.

        Single-turn only (no conversation history for MVP).

        Args:
            question: The user's plain-English data question.

        Returns:
            BrainResponse with text summary, SQL, data, and suggested
            chart type.

        Raises:
            BrainError: If all retries exhausted or unrecoverable error.
        """
        ...


# ── CHART ENGINE INTERFACE ──


class ChartEngineInterface(ABC):
    """Contract for the Visualization Engine.

    Consumed by: app/orchestrator.py.
    """

    @abstractmethod
    def render(self, request: ChartRequest) -> ChartResult:
        """Generate a chart from structured data.

        The engine infers x/y axes if not explicitly provided
        in the ChartRequest.

        Args:
            request: ChartRequest containing data, chart type, and config.

        Returns:
            ChartResult with image bytes.

        Raises:
            EmptyDataError:            No plottable rows.
            DataTypeMismatchError:     Column types conflict with chart.
            UnsupportedChartTypeError: Unrecognised chart type.
        """
        ...

    @abstractmethod
    def supported_chart_types(self) -> list[ChartType]:
        """Return list of chart types this engine can produce.

        Returns:
            List of ChartType enum values that the engine supports.
        """
        ...


# ── ORCHESTRATOR INTERFACE ──


class OrchestratorInterface(ABC):
    """Contract for the top-level app orchestrator.

    Consumed by: Gateway module (router.py calls this).
    """

    @abstractmethod
    async def handle_question(self, request: SlackRequest) -> SlackResponse:
        """Full Slack pipeline: question -> Brain -> DB -> Viz -> SlackResponse.

        Convenience wrapper around compute_answer() that also performs
        Slack-specific delivery (chart upload, thread reply formatting).
        This is the entry point the Gateway calls.

        Args:
            request: Normalized SlackRequest from the gateway.

        Returns:
            SlackResponse ready to be sent back to the Slack channel.
        """
        ...

    @abstractmethod
    async def compute_answer(
        self,
        question: str,
        brain_override: "BrainInterface | None" = None,
    ) -> AnswerResult:
        """Run the brain → viz pipeline for one question, transport-agnostic.

        Does NOT touch Slack. Returns a plain AnswerResult that any I/O
        surface (Slack gateway, web UI, future surfaces) can format.
        This is the seam that lets the same brain pipeline serve both
        Slack and a hosted web demo.

        Args:
            question: The user's plain-English data question.
            brain_override: Optional per-request brain. When set, used
                instead of the orchestrator's default brain. The web
                layer passes a session-scoped brain here so uploaded
                CSV sessions route to their own DB; Slack passes None
                and uses the shared mock-data brain.

        Returns:
            AnswerResult with text, optional query_result, optional
            chart bytes, error message on failure, and latency measurement.
        """
        ...
