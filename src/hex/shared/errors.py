"""Shared exception types for the Hex Analytics Bot.

All custom exceptions are defined here. Modules raise these specific
error types so callers can handle failures precisely without depending
on internal implementation details.
"""


class HexError(Exception):
    """Base exception for the entire Hex project.

    All custom exceptions inherit from this, allowing broad catch-all
    handling when needed.
    """


# ── Database errors ──


class DatabaseError(HexError):
    """Base for all DB execution errors.

    Attributes:
        original_sql: The SQL string that caused the error.
    """

    def __init__(self, message: str, original_sql: str = ""):
        """Initialize DatabaseError with message and optional SQL.

        Args:
            message:      Human-readable error description.
            original_sql: The SQL that triggered the error.
        """
        self.original_sql = original_sql
        super().__init__(message)

    def to_dict(self) -> dict[str, str]:
        """Serialize error to a dictionary for logging or API responses.

        Returns:
            Dict with error_type, message, and original_sql keys.
        """
        return {
            "error_type": self.__class__.__name__,
            "message": str(self),
            "original_sql": self.original_sql,
        }


class QuerySyntaxError(DatabaseError):
    """Malformed SQL that cannot be parsed or prepared."""


class ForbiddenQueryError(DatabaseError):
    """Blocked operation (writes, DROP, ALTER, etc.)."""


class QueryExecutionError(DatabaseError):
    """Runtime error during query execution (bad column, timeout, etc.)."""


class CSVValidationError(HexError):
    """Uploaded CSV failed parsing or exceeded a configured limit.

    Raised by the CSV loader for any rejection the user can act on
    (oversized, malformed, empty, non-UTF-8, too many columns/rows).
    Deliberately separate from DatabaseError because the CSV never
    reached SQL execution — it was rejected upstream.
    """


# ── Brain errors ──


class BrainError(HexError):
    """Base for all Brain module errors."""


class LLMError(BrainError):
    """Claude API failures (base for specific API error types)."""


class LLMRateLimitError(LLMError):
    """429 Too Many Requests from the Claude API."""


class LLMTimeoutError(LLMError):
    """Request timeout when calling the Claude API."""


class LLMResponseParseError(LLMError):
    """LLM response was not valid JSON or had unexpected structure."""


class SQLGenerationError(BrainError):
    """LLM produced invalid or unsafe SQL after all retries."""


class WriteOperationDetected(SQLGenerationError):
    """SQL contains INSERT/UPDATE/DELETE/DROP — immediately fatal, no retry."""


# ── Visualization errors ──


class VisualizationError(HexError):
    """Base for all Viz module errors."""


class EmptyDataError(VisualizationError):
    """No plottable rows in the provided data."""


class DataTypeMismatchError(VisualizationError):
    """Column data types are incompatible with the requested chart type."""


class UnsupportedChartTypeError(VisualizationError):
    """Unrecognized or unsupported chart type was requested."""


# ── Gateway errors ──


class GatewayError(HexError):
    """Base for all Gateway module errors."""


class SlackConnectionError(GatewayError):
    """Failed to establish connection to Slack (Socket Mode)."""


class DuplicateEventError(GatewayError):
    """Event has already been processed (idempotency guard)."""


class EventValidationError(GatewayError):
    """Incoming Slack event is missing required fields."""


class ResponseDeliveryError(GatewayError):
    """Failed to post response back to Slack channel."""
