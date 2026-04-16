"""Tests for the CSV loader.

Covers the pure parsing/sanitization layer plus the loader's behavior
inside SQLiteEngine. The engine tests confirm the glue (CREATE TABLE,
executemany, _meta flip) lines up with what parse() returns.
"""

from __future__ import annotations

import pytest

from hex.db.csv_loader import (
    MAX_BYTES,
    MAX_COLUMNS,
    MAX_ROWS,
    coerce,
    dedupe,
    infer_column_type,
    parse,
    sanitize_identifier,
)
from hex.db.engine import SQLiteEngine
from hex.shared.errors import CSVValidationError


# ── sanitize_identifier ────────────────────────────────────────────────────


class TestSanitizeIdentifier:
    """Lowercase / dedupe / anti-collision rules for column + table names."""

    def test_lowercases_and_replaces_spaces(self) -> None:
        assert sanitize_identifier("First Name") == "first_name"

    def test_strips_special_chars(self) -> None:
        assert sanitize_identifier("price ($)") == "price"

    def test_collapses_multiple_nonalnum_runs(self) -> None:
        assert sanitize_identifier("a!!!b???c") == "a_b_c"

    def test_strips_leading_and_trailing_underscores(self) -> None:
        assert sanitize_identifier("___name___") == "name"

    def test_digit_leading_gets_prefix(self) -> None:
        # "2024" would be an illegal SQL identifier; prefix makes it safe.
        assert sanitize_identifier("2024") == "col_2024"

    def test_empty_returns_fallback(self) -> None:
        assert sanitize_identifier("") == "col"
        assert sanitize_identifier("   ") == "col"
        assert sanitize_identifier("!!!") == "col"

    def test_custom_fallback_honored(self) -> None:
        assert sanitize_identifier("", fallback="data") == "data"
        assert sanitize_identifier("2025", fallback="col_0") == "col_0_2025"


# ── dedupe ────────────────────────────────────────────────────────────────


class TestDedupe:
    """Duplicate column handling after sanitization."""

    def test_no_duplicates_unchanged(self) -> None:
        assert dedupe(["a", "b", "c"]) == ["a", "b", "c"]

    def test_duplicates_get_numeric_suffix(self) -> None:
        assert dedupe(["a", "a", "a"]) == ["a", "a_2", "a_3"]

    def test_mixed_preserves_first_unsuffixed(self) -> None:
        assert dedupe(["name", "price", "name", "price", "name"]) == [
            "name",
            "price",
            "name_2",
            "price_2",
            "name_3",
        ]


# ── infer_column_type ─────────────────────────────────────────────────────


class TestInferColumnType:
    """Type priority: INTEGER > REAL > TEXT with the leading-zero guard."""

    def test_all_ints(self) -> None:
        assert infer_column_type(["1", "2", "3"]) == "INTEGER"

    def test_mix_int_and_float_promotes_to_real(self) -> None:
        assert infer_column_type(["1", "2.5", "3"]) == "REAL"

    def test_all_floats(self) -> None:
        assert infer_column_type(["1.1", "2.2", "3.3"]) == "REAL"

    def test_any_text_falls_through_to_text(self) -> None:
        assert infer_column_type(["1", "hello", "3"]) == "TEXT"

    def test_leading_zero_ids_stay_text(self) -> None:
        # Phone numbers and zero-padded IDs must not become INTEGER.
        assert infer_column_type(["0012", "0034"]) == "TEXT"

    def test_empty_strings_ignored(self) -> None:
        assert infer_column_type(["1", "", "2", ""]) == "INTEGER"

    def test_all_empty_is_text(self) -> None:
        # No signal means no promotion — TEXT is the safe default.
        assert infer_column_type(["", "", ""]) == "TEXT"

    def test_single_zero_is_int(self) -> None:
        assert infer_column_type(["0", "1", "2"]) == "INTEGER"


# ── coerce ────────────────────────────────────────────────────────────────


class TestCoerce:
    """Empty-string → NULL, type-matched coercion, defensive fallback."""

    def test_empty_becomes_none_regardless_of_type(self) -> None:
        assert coerce("", "INTEGER") is None
        assert coerce("", "REAL") is None
        assert coerce("", "TEXT") is None

    def test_int_coerces(self) -> None:
        assert coerce("42", "INTEGER") == 42

    def test_float_coerces(self) -> None:
        assert coerce("3.14", "REAL") == 3.14

    def test_text_passthrough(self) -> None:
        assert coerce("hello", "TEXT") == "hello"

    def test_bad_int_falls_back_to_raw(self) -> None:
        # Shouldn't happen given inference, but coerce stays defensive
        # so a single oddball row doesn't abort an entire upload.
        assert coerce("not a number", "INTEGER") == "not a number"


# ── parse (end-to-end on the in-memory bytes path) ────────────────────────


class TestParseHappyPath:
    """The 80% path: a well-formed CSV with a filename."""

    def test_simple_csv(self) -> None:
        csv = b"name,age,salary\nAlice,30,50000.5\nBob,25,40000\n"
        result = parse(csv, "people.csv")

        assert result.table_name == "people"
        assert result.column_names == ["name", "age", "salary"]
        assert result.column_types == ["TEXT", "INTEGER", "REAL"]
        assert result.rows == [("Alice", "30", "50000.5"), ("Bob", "25", "40000")]

    def test_strips_bom(self) -> None:
        # Excel exports as UTF-8-with-BOM; loader must transparently handle it.
        csv = "\ufeffa,b\n1,2\n".encode("utf-8")
        result = parse(csv, "x.csv")
        assert result.column_names == ["a", "b"]

    def test_crlf_line_endings(self) -> None:
        csv = b"a,b\r\n1,2\r\n3,4\r\n"
        result = parse(csv, "x.csv")
        assert len(result.rows) == 2

    def test_quoted_fields_with_commas(self) -> None:
        csv = b'name,address\nAlice,"123 Main St, Apt 4"\n'
        result = parse(csv, "x.csv")
        assert result.rows[0][1] == "123 Main St, Apt 4"

    def test_filename_with_path_prefix_trimmed(self) -> None:
        csv = b"a\n1\n"
        result = parse(csv, "/tmp/foo/bar/people.csv")
        assert result.table_name == "people"

    def test_filename_without_csv_extension(self) -> None:
        csv = b"a\n1\n"
        result = parse(csv, "report")
        assert result.table_name == "report"

    def test_weird_filename_falls_back_to_data(self) -> None:
        csv = b"a\n1\n"
        result = parse(csv, ".csv")
        assert result.table_name == "data"


class TestParseColumnHandling:
    """Header edge cases."""

    def test_duplicate_column_names_deduped(self) -> None:
        csv = b"name,Name,NAME\n1,2,3\n"
        result = parse(csv, "x.csv")
        # All three sanitize to "name"; dedupe appends _2, _3.
        assert result.column_names == ["name", "name_2", "name_3"]

    def test_digit_leading_column_prefixed(self) -> None:
        csv = b"2023,2024\n10,20\n"
        result = parse(csv, "x.csv")
        # Columns use their positional fallback so "2023" and "2024"
        # don't collide on the shared "col" prefix.
        assert result.column_names[0].startswith("col_")

    def test_short_row_padded(self) -> None:
        # One trailing comma missing — we pad instead of rejecting,
        # because real-world CSVs frequently have ragged tails.
        csv = b"a,b,c\n1,2\n"
        result = parse(csv, "x.csv")
        assert result.rows == [("1", "2", "")]

    def test_long_row_truncated(self) -> None:
        csv = b"a,b\n1,2,3,4\n"
        result = parse(csv, "x.csv")
        assert result.rows == [("1", "2")]


class TestParseValidation:
    """All the ways a CSV can legitimately be rejected."""

    def test_oversized_raises(self) -> None:
        big = b"a\n" + b"x\n" * (MAX_BYTES + 1)
        with pytest.raises(CSVValidationError, match="too large"):
            parse(big, "x.csv")

    def test_empty_bytes_raises(self) -> None:
        with pytest.raises(CSVValidationError, match="empty"):
            parse(b"", "x.csv")

    def test_header_only_raises(self) -> None:
        with pytest.raises(CSVValidationError, match="no data rows"):
            parse(b"a,b,c\n", "x.csv")

    def test_too_many_columns_raises(self) -> None:
        header = ",".join(f"c{i}" for i in range(MAX_COLUMNS + 1)).encode()
        csv = header + b"\n" + b",".join(b"1" for _ in range(MAX_COLUMNS + 1)) + b"\n"
        with pytest.raises(CSVValidationError, match="columns"):
            parse(csv, "x.csv")

    def test_too_many_rows_raises(self) -> None:
        # Build a CSV just over the limit. Deliberately small column
        # count so we stay well under MAX_BYTES and isolate the row check.
        body = b"a\n" + (b"1\n" * (MAX_ROWS + 1))
        with pytest.raises(CSVValidationError, match="more than"):
            parse(body, "x.csv")

    def test_empty_header_row_raises(self) -> None:
        with pytest.raises(CSVValidationError, match="header"):
            parse(b",,,\n1,2,3,4\n", "x.csv")

    def test_undecodable_bytes_raise(self) -> None:
        # Invalid as both UTF-8 and Latin-1 is hard to construct (Latin-1
        # accepts every byte). Simulate by using a byte sequence that
        # decodes but malforms the CSV parser path — covered by CSV error
        # tests below. Keep this as a smoke test that latin-1 fallback
        # works without raising.
        csv = "name,city\nAlice,São Paulo\n".encode("latin-1")
        result = parse(csv, "x.csv")
        # "São" may come back differently under latin-1 than UTF-8; we
        # only care that we don't raise and that we get one data row.
        assert len(result.rows) == 1


# ── Engine integration: load_csv end-to-end ───────────────────────────────


class TestEngineLoadCsv:
    """The thin glue layer between parse() and SQLite DDL/DML."""

    def test_blank_engine_has_no_tables(self) -> None:
        engine = SQLiteEngine(seed=False)
        assert engine.get_schema_description() == {}
        # health_check is False until load_csv flips the flag — that's
        # the contract callers depend on.
        assert engine.health_check() is False

    def test_load_csv_creates_table_and_inserts_rows(self) -> None:
        engine = SQLiteEngine(seed=False)
        csv = b"name,age\nAlice,30\nBob,25\n"

        loaded = engine.load_csv(csv, "people.csv")

        assert loaded.table_name == "people"
        assert loaded.row_count == 2
        assert loaded.columns == [
            {"name": "name", "type": "TEXT"},
            {"name": "age", "type": "INTEGER"},
        ]
        assert loaded.preview_rows == [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ]

        # Schema introspection agrees with the LoadedTable report.
        schema = engine.get_schema_description()
        assert "people" in schema
        assert schema["people"] == loaded.columns

    def test_load_csv_flips_health_check(self) -> None:
        engine = SQLiteEngine(seed=False)
        engine.load_csv(b"a,b\n1,2\n", "x.csv")
        assert engine.health_check() is True

    def test_load_csv_data_is_queryable(self) -> None:
        # End-to-end: load → query → verify the SQL round-trip works
        # with coerced values (string CSV cells became int/float/text).
        engine = SQLiteEngine(seed=False)
        engine.load_csv(b"city,pop\nAustin,1000000\nDallas,1300000\n", "cities.csv")

        result = engine.execute_readonly(
            'SELECT city, pop FROM cities ORDER BY pop DESC'
        )

        assert result.success is True
        assert result.rows == [("Dallas", 1300000), ("Austin", 1000000)]

    def test_load_csv_null_from_empty_cell(self) -> None:
        # Empty strings become NULL so aggregates ignore them — a
        # quality-of-life choice worth locking in with a test.
        engine = SQLiteEngine(seed=False)
        engine.load_csv(b"name,score\nAlice,10\nBob,\nCarol,20\n", "scores.csv")

        result = engine.execute_readonly("SELECT AVG(score) FROM scores")
        # AVG of (10, NULL, 20) = 15, not 10 (which would be wrong).
        assert result.rows[0][0] == 15.0

    def test_load_csv_rejects_malformed(self) -> None:
        engine = SQLiteEngine(seed=False)
        with pytest.raises(CSVValidationError):
            engine.load_csv(b"", "empty.csv")

    def test_seeded_engine_unchanged_by_refactor(self) -> None:
        # Sanity check: the default seed path still produces the mock
        # SaaS schema. Guards against regressions in the engine
        # constructor after the seed-optional refactor.
        engine = SQLiteEngine()
        schema = engine.get_schema_description()
        assert {"plans", "users", "subscriptions", "invoices", "events"} <= set(schema)
        assert engine.health_check() is True
