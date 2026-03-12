"""Retry handler for SQL generation and execution.

Manages the correction loop when DB execution fails: re-prompts the LLM
with the error message and previous SQL to get a corrected query.
Wraps synchronous DB calls in asyncio.to_thread().
"""

import asyncio
import logging

from hex.shared.errors import (
    DatabaseError,
    LLMRateLimitError,
    LLMTimeoutError,
    SQLGenerationError,
    WriteOperationDetected,
)
from hex.shared.interfaces import DatabaseEngineInterface
from hex.shared.models import GeneratedSQL, QueryResult

from hex.brain.llm_client import LLMClient
from hex.brain.sql_validator import check

logger = logging.getLogger(__name__)


class RetryHandler:
    """Handles SQL execution with correction retries on failure.

    Receives the DB engine and LLM client via constructor injection.
    On DB errors, re-prompts Claude with the correction template.
    On WriteOperationDetected, fails immediately without retry.

    Attributes:
        _db:         DatabaseEngineInterface for query execution.
        _llm:        LLMClient for correction re-prompts.
        _max_retries: Maximum number of SQL correction retries.
    """

    def __init__(
        self,
        db_engine: DatabaseEngineInterface,
        llm_client: LLMClient,
        max_retries: int = 2,
    ) -> None:
        """Initialize the retry handler with dependencies.

        Args:
            db_engine:   The database engine for executing queries.
            llm_client:  The LLM client for correction re-prompts.
            max_retries: Maximum SQL correction retries (default 2).
        """
        self._db = db_engine
        self._llm = llm_client
        self._max_retries = max_retries

    async def execute_with_retries(
        self,
        generated: GeneratedSQL,
        question: str,
        system_prompt: str,
    ) -> tuple[QueryResult, int]:
        """Execute generated SQL with automatic retry on DB errors.

        Flow:
        1. Validate SQL with Brain's sql_validator
        2. Execute via DB engine (wrapped in asyncio.to_thread)
        3. On DB error: re-prompt LLM with correction template
        4. On WriteOperationDetected: fail immediately (no retry)
        5. On LLMRateLimitError: exponential backoff up to 3 API retries
        6. On LLMTimeoutError: retry once then fail

        Args:
            generated:     The initial GeneratedSQL from the LLM.
            question:      The original user question.
            system_prompt: The system prompt for correction re-prompts.

        Returns:
            Tuple of (QueryResult, retries_used).

        Raises:
            WriteOperationDetected: If SQL contains write operations.
            SQLGenerationError: If all retries are exhausted.
        """
        current_sql = generated.sql
        retries_used = 0

        for attempt in range(self._max_retries + 1):
            # Validate SQL safety
            check(current_sql)

            try:
                # Wrap sync DB call in asyncio.to_thread
                result = await asyncio.to_thread(
                    self._db.execute_readonly, current_sql
                )
                return result, retries_used

            except WriteOperationDetected:
                # Fatal — do not retry
                raise

            except DatabaseError as db_err:
                retries_used += 1
                logger.warning(
                    "DB execution failed (attempt %d/%d): %s",
                    attempt + 1,
                    self._max_retries + 1,
                    str(db_err),
                )

                if attempt >= self._max_retries:
                    raise SQLGenerationError(
                        f"SQL generation failed after {retries_used} retries: {db_err}"
                    ) from db_err

                # Re-prompt LLM for correction
                try:
                    current_sql = await self._correct_sql(
                        question, current_sql, str(db_err), system_prompt
                    )
                except (LLMRateLimitError, LLMTimeoutError) as llm_err:
                    raise SQLGenerationError(
                        f"LLM unavailable during correction: {llm_err}"
                    ) from llm_err

        # Should not reach here, but safety net
        raise SQLGenerationError("Max retries exhausted")

    async def _correct_sql(
        self,
        question: str,
        previous_sql: str,
        error: str,
        system_prompt: str,
    ) -> str:
        """Re-prompt the LLM to correct failed SQL.

        Args:
            question:     Original user question.
            previous_sql: The SQL that failed.
            error:        Error message from the DB.
            system_prompt: System prompt for context.

        Returns:
            The corrected SQL string from the LLM.

        Raises:
            LLMRateLimitError: If rate limited during correction.
            LLMTimeoutError: If the correction call times out.
            SQLGenerationError: If the correction response can't be parsed.
        """
        correction_prompt = self._llm.build_correction_prompt(
            question, previous_sql, error
        )

        raw_response = await self._llm.generate(system_prompt, correction_prompt)
        parsed = self._llm.parse_response(raw_response)

        if parsed.sql is None:
            raise SQLGenerationError(
                "LLM returned null SQL during correction — giving up"
            )

        logger.info("LLM provided corrected SQL: %s", parsed.sql[:100])
        return parsed.sql
