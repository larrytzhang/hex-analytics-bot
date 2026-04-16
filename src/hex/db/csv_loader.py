"""Pure helpers for turning a user-uploaded CSV into a SQLite table.

The web layer accepts a CSV over HTTP, hands the raw bytes to
``SQLiteEngine.load_csv``, and gets back a :class:`LoadedTable`. All
parsing, identifier sanitization, type inference, and limit enforcement
live here — the engine only orchestrates the SQL writes. This split
keeps the engine small and makes the validation rules cheap to unit-test
without spinning up a database.

Limits are deliberately conservative because the endpoint is
unauthenticated on the public demo: a 5 MB / 10k-row / 50-col cap
keeps worst-case memory bounded even with several concurrent uploads.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from typing import Iterable

from hex.shared.errors import CSVValidationError


# ── Limits ──────────────────────────────────────────────────────────────
# These are intentional soft limits for the demo. Enforced at parse time
# so a pathological CSV can't exhaust memory or starve the event loop.

MAX_BYTES = 5 * 1024 * 1024  # 5 MB raw payload
MAX_ROWS = 10_000            # Excludes header
MAX_COLUMNS = 50
TYPE_SAMPLE_SIZE = 200        # Rows sampled for type inference; enough
                              # to catch mixed-type columns without
                              # scanning the whole file.


@dataclass(frozen=True)
class ParsedCSV:
    """Output of the pure parse step, before any SQL is executed.

    Kept separate from :class:`~hex.shared.models.LoadedTable` because
    ``LoadedTable`` carries the final ``row_count`` and preview rows the
    UI renders — those are only known after the loader actually inserts
    data. Think of this as the intermediate representation between bytes
    and SQL.

    Attributes:
        table_name:    Sanitized table identifier.
        column_names:  Sanitized column identifiers, in order.
        column_types:  Inferred SQL types (INTEGER/REAL/TEXT), parallel
                       to ``column_names``.
        rows:          All data rows as tuples of strings (raw CSV cells,
                       still un-coerced — the engine coerces per column
                       type during insertion).
    """

    table_name: str
    column_names: list[str]
    column_types: list[str]
    rows: list[tuple[str, ...]]


# ── Identifier sanitization ─────────────────────────────────────────────


# Strip anything that isn't safe inside a SQLite identifier. We can't
# trust user CSVs to have clean column names: ``"First Name"``,
# ``"2024 Q1"``, ``"price ($)"`` all need to survive. Quoting identifiers
# would also work but makes the LLM prompt noisier — plain snake_case is
# easier on everyone downstream.
_SAFE_CHAR = re.compile(r"[^a-z0-9_]+")


def sanitize_identifier(raw: str, *, fallback: str = "col") -> str:
    """Convert an arbitrary string into a safe SQLite identifier.

    Rules:
      - Lowercase.
      - Non-alphanumeric runs collapse to a single underscore.
      - Leading/trailing underscores stripped.
      - If empty after cleaning, returns ``fallback``.
      - If starts with a digit, prefixed with ``fallback + "_"``.

    The SQLite keyword list is intentionally NOT checked — all
    identifiers we emit are quoted during DDL/DML where it matters, and
    we prefer predictable output over a keyword blacklist that drifts.

    Args:
        raw:      Input string (column name, table name, etc.).
        fallback: Used when ``raw`` sanitizes to an empty string or
                  starts with a digit. Keeps column names like ``"2024"``
                  from colliding with SQL numeric literals.

    Returns:
        A non-empty snake_case string safe to use as a SQL identifier.
    """
    # Lowercase first so we don't have to case-fold repeatedly.
    cleaned = _SAFE_CHAR.sub("_", raw.strip().lower()).strip("_")
    if not cleaned:
        return fallback
    # SQL identifiers can't start with a digit; prefix instead of
    # rejecting, because rejection would surprise users who label columns
    # with years ("2024", "2025 revenue").
    if cleaned[0].isdigit():
        return f"{fallback}_{cleaned}"
    return cleaned


def dedupe(names: Iterable[str]) -> list[str]:
    """Return the input sequence with duplicates suffixed ``_2, _3, ...``.

    After :func:`sanitize_identifier`, two distinct headers can collapse
    to the same string (``"Price $"`` and ``"price"`` both become
    ``price``). SQL would reject that as a duplicate column name, so we
    suffix. Order is preserved so column positions stay stable for the
    user.

    Args:
        names: Iterable of already-sanitized identifiers.

    Returns:
        List of identifiers with duplicates disambiguated by numeric
        suffix.
    """
    seen: dict[str, int] = {}
    out: list[str] = []
    for name in names:
        if name not in seen:
            seen[name] = 1
            out.append(name)
        else:
            seen[name] += 1
            out.append(f"{name}_{seen[name]}")
    return out


# ── Type inference ──────────────────────────────────────────────────────


def _is_int_like(v: str) -> bool:
    """Whether ``v`` looks like a plain integer (and not a zero-padded ID).

    Zero-padded strings ("007", "0123") are kept as TEXT so we don't
    silently destroy leading zeros — that's a common data-quality
    landmine for phone numbers, ZIP codes, and legacy IDs.
    """
    if not v:
        return False
    try:
        int(v)
    except ValueError:
        return False
    # Reject leading-zero multi-digit strings ("0" alone is fine).
    return not (len(v) > 1 and v.startswith("0") and v[1] != ".")


def _is_float_like(v: str) -> bool:
    """Whether ``v`` parses as a float *and* has an explicit decimal/exponent.

    The explicit-marker requirement is load-bearing: ``"0012"`` parses
    as float(12.0), but it's a zero-padded ID the user wants kept as
    TEXT, not a numeric measurement. Requiring "." or "e/E" means a
    column of zero-padded strings never gets promoted past TEXT, while
    real floats like ``"3.14"`` or ``"1e-5"`` still qualify.
    """
    if not v:
        return False
    if "." not in v and "e" not in v and "E" not in v:
        return False
    try:
        float(v)
    except ValueError:
        return False
    return True


def infer_column_type(samples: Iterable[str]) -> str:
    """Return the SQLite column type best fitting the sampled values.

    Priority is INTEGER → REAL → TEXT. Empty strings are ignored so a
    sparse column doesn't get demoted to TEXT just because half its
    cells are blank. If every non-empty sample is blank (i.e. the
    column is entirely empty in the sample window), we default to TEXT
    — safer than guessing INTEGER for a field we've never seen a value
    in.

    Args:
        samples: The first N raw string values from a CSV column.

    Returns:
        One of ``"INTEGER"``, ``"REAL"``, ``"TEXT"``.
    """
    non_empty = [s for s in samples if s != ""]
    if not non_empty:
        return "TEXT"
    if all(_is_int_like(s) for s in non_empty):
        return "INTEGER"
    if all(_is_int_like(s) or _is_float_like(s) for s in non_empty):
        return "REAL"
    return "TEXT"


# ── Main parse entry point ──────────────────────────────────────────────


def parse(csv_bytes: bytes, filename_hint: str) -> ParsedCSV:
    """Decode, validate, and structure a raw CSV payload.

    Pure function — no IO, no database access. All limit checks run
    before building the row list so an oversized file never allocates
    the full structure.

    Args:
        csv_bytes:     Raw CSV bytes as received over HTTP.
        filename_hint: Original filename; used to derive the table name
                       when the CSV itself doesn't carry one.

    Returns:
        :class:`ParsedCSV` with sanitized identifiers, inferred types,
        and all data rows as string tuples.

    Raises:
        CSVValidationError: On any limit violation, malformed CSV, or
            unreadable encoding. Message is user-facing.
    """
    # 1. Size guard — cheap, run first.
    if len(csv_bytes) > MAX_BYTES:
        mb = MAX_BYTES // (1024 * 1024)
        raise CSVValidationError(
            f"CSV is too large ({len(csv_bytes):,} bytes). Max is {mb} MB."
        )
    if len(csv_bytes) == 0:
        raise CSVValidationError("CSV file is empty.")

    # 2. Decode. UTF-8 covers 99% of real-world CSVs; latin-1 is the
    # common fallback for Excel exports. Anything else is rejected with
    # a clear message rather than silently mangled.
    try:
        text = csv_bytes.decode("utf-8-sig")  # -sig strips BOM.
    except UnicodeDecodeError:
        try:
            text = csv_bytes.decode("latin-1")
        except UnicodeDecodeError as e:
            raise CSVValidationError(
                "CSV encoding is not UTF-8 or Latin-1. Re-save as UTF-8 and retry."
            ) from e

    # 3. Parse header + rows. ``csv.reader`` handles quoted fields,
    # embedded newlines, and CRLF line endings natively.
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        raise CSVValidationError("CSV has no rows.") from None
    except csv.Error as e:
        raise CSVValidationError(f"CSV is malformed: {e}") from e

    if not header or all(cell.strip() == "" for cell in header):
        raise CSVValidationError("CSV header row is empty.")
    if len(header) > MAX_COLUMNS:
        raise CSVValidationError(
            f"CSV has {len(header)} columns; max is {MAX_COLUMNS}."
        )

    # 4. Sanitize + dedupe column names.
    raw_columns = [sanitize_identifier(h, fallback=f"col_{i}") for i, h in enumerate(header)]
    column_names = dedupe(raw_columns)

    # 5. Read data rows. Enforce MAX_ROWS as we go — a generator-style
    # loop so we stop scanning rather than reading the whole file first.
    rows: list[tuple[str, ...]] = []
    expected_width = len(column_names)
    try:
        for row in reader:
            if len(rows) >= MAX_ROWS:
                raise CSVValidationError(
                    f"CSV has more than {MAX_ROWS:,} data rows. "
                    "Trim the file or sample a subset."
                )
            # Pad short rows with empty strings; truncate over-long rows.
            # Being lenient here beats failing the whole upload because
            # one row has a trailing comma.
            if len(row) < expected_width:
                row = row + [""] * (expected_width - len(row))
            elif len(row) > expected_width:
                row = row[:expected_width]
            rows.append(tuple(row))
    except csv.Error as e:
        raise CSVValidationError(f"CSV is malformed: {e}") from e

    if not rows:
        raise CSVValidationError("CSV has a header but no data rows.")

    # 6. Infer types from the first TYPE_SAMPLE_SIZE rows per column.
    # Sampling is bounded so a 10k-row upload doesn't spend seconds in
    # inference — the first 200 rows are representative enough.
    column_types: list[str] = []
    for col_idx in range(expected_width):
        samples = [r[col_idx] for r in rows[:TYPE_SAMPLE_SIZE]]
        column_types.append(infer_column_type(samples))

    # 7. Derive table name from the filename hint. ``report-2025.csv`` →
    # ``report_2025``. Falls back to ``data`` if the filename sanitizes
    # to nothing (e.g. ".csv", "   .csv").
    stem = filename_hint.rsplit("/", 1)[-1]      # Trim any path prefix.
    if stem.lower().endswith(".csv"):
        stem = stem[:-4]
    table_name = sanitize_identifier(stem, fallback="data")

    return ParsedCSV(
        table_name=table_name,
        column_names=column_names,
        column_types=column_types,
        rows=rows,
    )


def coerce(value: str, sql_type: str) -> object | None:
    """Convert a raw CSV string cell into the Python value SQLite expects.

    Empty strings become NULL (``None``) so aggregations like ``AVG()``
    ignore them naturally. ``TEXT`` columns pass through verbatim,
    including whitespace, so the user's data isn't silently mutated.

    Args:
        value:    Raw CSV cell content.
        sql_type: The inferred column type (INTEGER/REAL/TEXT).

    Returns:
        ``None``, ``int``, ``float``, or ``str`` — whichever matches
        ``sql_type``. If an INTEGER/REAL cell fails to parse (shouldn't
        happen given inference, but defensive), we fall back to the
        raw string so the insert still succeeds.
    """
    if value == "":
        return None
    if sql_type == "INTEGER":
        try:
            return int(value)
        except ValueError:
            return value
    if sql_type == "REAL":
        try:
            return float(value)
        except ValueError:
            return value
    return value
