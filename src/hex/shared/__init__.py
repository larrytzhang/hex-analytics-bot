"""Shared module — canonical types, interfaces, and errors.

Re-exports all public symbols for convenient importing.
Usage: from hex.shared import QueryResult, BrainInterface, HexError
"""

# ── Models ──
from hex.shared.models import (
    BrainResponse,
    ChartRequest,
    ChartResult,
    ChartType,
    ColumnMeta,
    GeneratedSQL,
    QueryResult,
    ResponseType,
    SemanticContext,
    SlackRequest,
    SlackResponse,
    TableMeta,
)

# ── Interfaces (ABCs) ──
from hex.shared.interfaces import (
    BrainInterface,
    ChartEngineInterface,
    DatabaseEngineInterface,
    OrchestratorInterface,
)

# ── Errors ──
from hex.shared.errors import (
    BrainError,
    DatabaseError,
    DataTypeMismatchError,
    DuplicateEventError,
    EmptyDataError,
    EventValidationError,
    ForbiddenQueryError,
    GatewayError,
    HexError,
    LLMError,
    LLMRateLimitError,
    LLMResponseParseError,
    LLMTimeoutError,
    QueryExecutionError,
    QuerySyntaxError,
    ResponseDeliveryError,
    SlackConnectionError,
    SQLGenerationError,
    UnsupportedChartTypeError,
    VisualizationError,
    WriteOperationDetected,
)

# ── Logging ──
from hex.shared.logging import configure_logging

__all__ = [
    # Models
    "BrainResponse",
    "ChartRequest",
    "ChartResult",
    "ChartType",
    "ColumnMeta",
    "GeneratedSQL",
    "QueryResult",
    "ResponseType",
    "SemanticContext",
    "SlackRequest",
    "SlackResponse",
    "TableMeta",
    # Interfaces
    "BrainInterface",
    "ChartEngineInterface",
    "DatabaseEngineInterface",
    "OrchestratorInterface",
    # Errors
    "BrainError",
    "DatabaseError",
    "DataTypeMismatchError",
    "DuplicateEventError",
    "EmptyDataError",
    "EventValidationError",
    "ForbiddenQueryError",
    "GatewayError",
    "HexError",
    "LLMError",
    "LLMRateLimitError",
    "LLMResponseParseError",
    "LLMTimeoutError",
    "QueryExecutionError",
    "QuerySyntaxError",
    "ResponseDeliveryError",
    "SlackConnectionError",
    "SQLGenerationError",
    "UnsupportedChartTypeError",
    "VisualizationError",
    "WriteOperationDetected",
    # Logging
    "configure_logging",
]
