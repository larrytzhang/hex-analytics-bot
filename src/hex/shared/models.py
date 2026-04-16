"""Canonical data models for the Hex Analytics Bot.

All domain objects, enums, and data classes used across modules are defined here.
No module should redefine these types locally — always import from this file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


# ── CHART TYPE (canonical — 10 values from Viz plan + NONE) ──


class ChartType(Enum):
    """Canonical chart type enum. Used by Brain (LLM output), Viz (rendering),
    and Orchestrator (routing).

    Values:
        BAR through TABLE: Specific chart rendering styles.
        AUTO: Let the Viz engine infer the best chart type from data shape.
        NONE: Brain uses this when no chart is appropriate for the answer.
    """

    BAR = "bar"
    GROUPED_BAR = "grouped_bar"
    STACKED_BAR = "stacked_bar"
    LINE = "line"
    MULTI_LINE = "multi_line"
    PIE = "pie"
    DONUT = "donut"
    SCATTER = "scatter"
    TABLE = "table"
    AUTO = "auto"
    NONE = "none"


# ── QUERY RESULT (canonical — unified from Brain + DB plans) ──


@dataclass(frozen=True)
class QueryResult:
    """Unified, immutable container for database query results.

    Used by: DB module (produces), Brain (consumes), Orchestrator (forwards
    to Viz), Viz (reads data for charting).

    Attributes:
        success:    Whether the query executed without error.
        columns:    Ordered list of column names in the result set.
        rows:       List of tuples, one per result row.
        row_count:  Number of rows returned or affected.
        query:      The original SQL string that was executed.
        error:      None on success; error message string on failure.
    """

    success: bool
    columns: list[str] = field(default_factory=list)
    rows: list[tuple[Any, ...]] = field(default_factory=list)
    row_count: int = 0
    query: str = ""
    error: str | None = None

    def to_dicts(self) -> list[dict[str, Any]]:
        """Convert rows to list of dicts keyed by column name.

        Returns:
            List of dictionaries where keys are column names and values are
            the corresponding row values. Primary format for Viz module consumption.
        """
        return [dict(zip(self.columns, row)) for row in self.rows]

    def to_json(self) -> str:
        """Serialize entire result to JSON string.

        Returns:
            JSON string containing success, columns, data (as dicts),
            row_count, query, and error fields.
        """
        return json.dumps(
            {
                "success": self.success,
                "columns": self.columns,
                "data": self.to_dicts(),
                "row_count": self.row_count,
                "query": self.query,
                "error": self.error,
            },
            default=str,
        )


# ── SEMANTIC CONTEXT (for LLM prompt injection) ──


@dataclass(frozen=True)
class ColumnMeta:
    """Metadata for a single database column.

    Attributes:
        name:          Column name as it appears in the schema.
        dtype:         SQL data type (e.g. "INTEGER", "TEXT", "REAL").
        description:   Human-readable purpose of the column.
        sample_values: Representative values for LLM context.
    """

    name: str
    dtype: str
    description: str
    sample_values: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TableMeta:
    """Metadata for a single database table.

    Attributes:
        name:        Table name as it appears in the schema.
        description: Human-readable purpose of the table.
        columns:     List of ColumnMeta describing each column.
    """

    name: str
    description: str
    columns: list[ColumnMeta]


@dataclass(frozen=True)
class SemanticContext:
    """Full schema context injected into the LLM prompt.

    Contains enriched metadata for all tables, the SQL dialect, and a
    business glossary mapping domain terms to their definitions.

    Attributes:
        tables:             List of TableMeta with enriched descriptions.
        dialect:            SQL dialect string (always "sqlite" for this project).
        business_glossary:  Maps business terms (e.g. "MRR") to definitions.
    """

    tables: list[TableMeta]
    dialect: str = "sqlite"
    business_glossary: dict[str, str] = field(default_factory=dict)


# ── LLM OUTPUT ──


@dataclass(frozen=True)
class GeneratedSQL:
    """Parsed output from the LLM after SQL generation.

    Attributes:
        sql:              The generated SQL query, or None if the LLM
                          determines it cannot answer the question.
        explanation:      Human-readable explanation of the query logic.
        suggested_chart:  Which chart type the LLM recommends for the results.
        confidence:       LLM's self-assessed confidence score (0.0 to 1.0).
    """

    sql: str | None
    explanation: str
    suggested_chart: ChartType
    confidence: float


# ── BRAIN RESPONSE ──


@dataclass
class BrainResponse:
    """Structured output from the Brain module to the Orchestrator.

    Attributes:
        text_summary:    Plain-English answer to the user's question.
        sql_used:        The SQL that was executed against the database.
        query_result:    The QueryResult from DB execution, or None on failure.
        suggested_chart: Which chart type the LLM recommended.
        error:           Error message if the pipeline failed, else None.
        retries_used:    Number of SQL correction retries that were needed.
    """

    text_summary: str
    sql_used: str
    query_result: QueryResult | None
    suggested_chart: ChartType
    error: str | None = None
    retries_used: int = 0


# ── CHART ARTIFACTS ──


@dataclass
class ChartRequest:
    """Everything the Viz module needs to produce a chart.

    Constructed by app/orchestrator.py from BrainResponse + QueryResult.

    Attributes:
        data:          Row-oriented dicts (from QueryResult.to_dicts()).
        chart_type:    Desired chart type (AUTO lets engine decide).
        title:         Chart title string.
        x_label:       X-axis label.
        y_label:       Y-axis label.
        x_column:      Column name for the x-axis, or None for auto-detect.
        y_columns:     Column name(s) for the y-axis, or None for auto-detect.
        group_column:  Column name for grouping (grouped/stacked bars).
        width:         Figure width in inches.
        height:        Figure height in inches.
        dpi:           Dots per inch for the output image.
    """

    data: list[dict[str, Any]]
    chart_type: ChartType = ChartType.AUTO
    title: str = ""
    x_label: str = ""
    y_label: str = ""
    x_column: str | None = None
    y_columns: list[str] | None = None
    group_column: str | None = None
    width: float = 10.0
    height: float = 6.0
    dpi: int = 150


@dataclass
class ChartResult:
    """What the Viz module hands back after rendering.

    Attributes:
        image_bytes: Raw PNG image bytes of the rendered chart.
        chart_type:  Actual chart type rendered (useful when AUTO was requested).
        metadata:    Optional metadata dict (e.g. axes info, render time).
    """

    image_bytes: bytes
    chart_type: ChartType
    metadata: dict[str, Any] = field(default_factory=dict)


# ── LOADED TABLE (metadata returned after user CSV upload) ──


@dataclass(frozen=True)
class LoadedTable:
    """Summary of a CSV the user uploaded and that was materialized into SQLite.

    Produced by the DB module's CSV loader, consumed by the web layer
    to build the upload response and the schema preview the UI renders.

    Attributes:
        table_name:    Sanitized SQL table name the CSV was loaded into.
        columns:       Column info as ``{name, type}`` dicts, matching
                       the shape of ``DatabaseEngineInterface.get_schema_description``
                       so the Brain can consume the same schema format
                       it already understands.
        row_count:     Number of data rows inserted (excludes header).
        preview_rows:  Up to 5 sample rows as dicts keyed by column name.
                       Used purely to render a "here's what got loaded"
                       preview in the UI — the Brain never sees these.
    """

    table_name: str
    columns: list[dict[str, str]]
    row_count: int
    preview_rows: list[dict[str, Any]] = field(default_factory=list)


# ── ANSWER RESULT (transport-agnostic — shared by Gateway and Web) ──


@dataclass
class AnswerResult:
    """Transport-agnostic output of the answer pipeline.

    Returned by AppOrchestrator._compute_answer(). Consumed by both the
    Slack gateway and the Web UI to format their respective responses.
    Keeping this separate from SlackResponse means the brain → viz
    pipeline can be reused by any I/O surface without leaking Slack
    types into web/.

    Attributes:
        text_summary:  Plain-English answer text from the Brain.
        query_result:  The QueryResult, or None when the question is
                       unanswerable or the Brain raised.
        chart_bytes:   Raw chart image bytes, or None when no chart was
                       generated (Brain suggested NONE, viz failed,
                       or the result was unsuitable for charting).
        chart_mime:    MIME type of chart_bytes. Always "image/png" today.
        error:         Human-friendly error message if the pipeline failed
                       in a way the user should see, else None.
        latency_ms:    Total wall-clock time for the pipeline in
                       milliseconds. Useful for observability and demo
                       transparency. Zero when not measured.
    """

    text_summary: str = ""
    query_result: QueryResult | None = None
    chart_bytes: bytes | None = None
    chart_mime: str = "image/png"
    error: str | None = None
    latency_ms: int = 0


# ── SLACK MODELS (used by Gateway + Orchestrator) ──


class ResponseType(Enum):
    """Type of response to send back to Slack.

    Values:
        TEXT:           Text-only response.
        IMAGE:          Image-only response.
        TEXT_AND_IMAGE: Combined text message plus chart image.
    """

    TEXT = auto()
    IMAGE = auto()
    TEXT_AND_IMAGE = auto()


@dataclass(frozen=True)
class SlackRequest:
    """Normalized incoming Slack event.

    Attributes:
        event_id:    Unique Slack event identifier (for dedup).
        team_id:     Slack workspace ID.
        channel_id:  Channel where the event occurred.
        thread_ts:   Thread timestamp for threading replies.
        message_ts:  Message timestamp.
        user_id:     Slack user ID who sent the message.
        raw_text:    Original message text including bot mention.
        clean_text:  Message text with bot mention stripped.
        received_at: ISO 8601 timestamp when the event was received.
    """

    event_id: str
    team_id: str
    channel_id: str
    thread_ts: str
    message_ts: str
    user_id: str
    raw_text: str
    clean_text: str
    received_at: str = ""


@dataclass
class SlackResponse:
    """Payload to send back to Slack.

    Attributes:
        channel_id:    Target channel for the response.
        thread_ts:     Thread timestamp to reply in-thread.
        response_type: Type of response (text, image, or both).
        text:          Text content of the response.
        image_bytes:   Raw PNG bytes for files_upload_v2, or None.
        alt_text:      Accessibility text for the uploaded image.
    """

    channel_id: str
    thread_ts: str
    response_type: ResponseType = ResponseType.TEXT
    text: str = ""
    image_bytes: bytes | None = None
    alt_text: str = ""
