"""Brain orchestrator — the internal pipeline for the Brain module.

Implements BrainInterface. Coordinates the full flow: load semantic context,
build prompts, call LLM, validate SQL, execute with retries, and return
a structured BrainResponse. All DB calls are wrapped in asyncio.to_thread().
"""

import asyncio
import logging

from hex.shared.errors import BrainError, LLMResponseParseError, SQLGenerationError, WriteOperationDetected
from hex.shared.interfaces import BrainInterface, DatabaseEngineInterface
from hex.shared.models import BrainResponse, ChartType, GeneratedSQL

from hex.brain.config import BrainConfig
from hex.brain.llm_client import LLMClient
from hex.brain.retry import RetryHandler
from hex.brain.semantic_layer import enrich
from hex.brain.sql_validator import check

logger = logging.getLogger(__name__)


class BrainOrchestrator(BrainInterface):
    """Concrete implementation of the Brain interface.

    Orchestrates the full question-to-answer pipeline:
    1. Get schema from DB (via asyncio.to_thread)
    2. Enrich schema into SemanticContext
    3. Build system + user prompts
    4. Call LLM for SQL generation
    5. Validate generated SQL
    6. Execute with retry loop
    7. Return structured BrainResponse

    NOTE: Does NOT call Viz. Returns suggested_chart in BrainResponse.
    The app/orchestrator handles Viz.

    Attributes:
        _config:       BrainConfig with model and retry settings.
        _db:           DatabaseEngineInterface for schema and execution.
        _llm:          LLMClient for Claude API calls.
        _retry_handler: RetryHandler for SQL correction loop.
    """

    def __init__(
        self,
        config: BrainConfig,
        db_engine: DatabaseEngineInterface,
        llm_client: LLMClient,
        *,
        use_glossary: bool = True,
    ) -> None:
        """Initialize the Brain orchestrator with all dependencies.

        Args:
            config:    BrainConfig with model and retry settings.
            db_engine: Database engine for schema access and query execution.
            llm_client: LLM client for Claude API interaction.
            use_glossary: When True (default) inject the SaaS business
                glossary (MRR, churn, DAU...) into the system prompt.
                Set False for user-uploaded CSVs — the glossary would
                just be noise against an arbitrary schema.
        """
        self._config = config
        self._db = db_engine
        self._llm = llm_client
        self._use_glossary = use_glossary
        self._retry_handler = RetryHandler(
            db_engine=db_engine,
            llm_client=llm_client,
            max_retries=config.max_sql_retries,
        )

    async def ask(self, question: str) -> BrainResponse:
        """Accept a plain-English question and return a structured answer.

        Full pipeline: schema -> semantic context -> prompt -> LLM ->
        validate -> execute -> BrainResponse.

        Args:
            question: The user's plain-English data question.

        Returns:
            BrainResponse with text summary, SQL used, query result,
            and suggested chart type.

        Raises:
            BrainError: If all retries are exhausted or an unrecoverable
                error occurs.
        """
        try:
            # Step 1: Get schema from DB (sync -> async wrapper)
            raw_schema = await asyncio.to_thread(self._db.get_schema_description)

            # Step 2: Enrich into SemanticContext
            context = enrich(raw_schema)

            # Step 3: Build prompts
            schema_text = self._format_schema(context)
            # Empty glossary for user-uploaded data — the SaaS terms
            # (MRR, churn) would just mislead the LLM against an
            # arbitrary schema it has no context for.
            glossary_text = self._format_glossary(context) if self._use_glossary else ""
            system_prompt = self._llm.build_system_prompt(schema_text, glossary_text)
            user_prompt = self._llm.build_user_prompt(question)

            # Step 4: Call LLM
            raw_response = await self._llm.generate(system_prompt, user_prompt)

            # Step 5: Parse response
            try:
                generated = self._llm.parse_response(raw_response)
            except LLMResponseParseError as e:
                return BrainResponse(
                    text_summary=f"I had trouble understanding the AI's response: {e}",
                    sql_used="",
                    query_result=None,
                    suggested_chart=ChartType.NONE,
                    error=str(e),
                )

            # Step 6: Handle unanswerable questions (sql is None)
            if generated.sql is None:
                table_names = [t.name for t in context.tables]
                return BrainResponse(
                    text_summary=(
                        f"{generated.explanation}\n\n"
                        f"I have access to these tables: {', '.join(table_names)}"
                    ),
                    sql_used="",
                    query_result=None,
                    suggested_chart=ChartType.NONE,
                )

            # Step 7: Validate and execute with retries
            query_result, retries_used = await self._retry_handler.execute_with_retries(
                generated, question, system_prompt
            )

            # Step 8: Build response with confidence warning if needed
            text_summary = generated.explanation
            if generated.confidence < 0.5:
                text_summary = f"Low confidence answer — please verify.\n\n{text_summary}"

            return BrainResponse(
                text_summary=text_summary,
                sql_used=generated.sql,
                query_result=query_result,
                suggested_chart=generated.suggested_chart,
                retries_used=retries_used,
            )

        except WriteOperationDetected as e:
            return BrainResponse(
                text_summary="I can only run read-only queries. Write operations are not allowed.",
                sql_used="",
                query_result=None,
                suggested_chart=ChartType.NONE,
                error=str(e),
            )

        except SQLGenerationError as e:
            return BrainResponse(
                text_summary=f"I wasn't able to generate a working query: {e}",
                sql_used="",
                query_result=None,
                suggested_chart=ChartType.NONE,
                error=str(e),
            )

        except BrainError as e:
            logger.error("Brain pipeline error: %s", str(e))
            raise

    def _format_schema(self, context) -> str:
        """Format SemanticContext tables into a string for the LLM prompt.

        Args:
            context: SemanticContext with enriched table metadata.

        Returns:
            Formatted schema string showing tables, columns, and descriptions.
        """
        lines = []
        for table in context.tables:
            lines.append(f"\nTable: {table.name}")
            lines.append(f"  Description: {table.description}")
            lines.append("  Columns:")
            for col in table.columns:
                lines.append(f"    - {col.name} ({col.dtype}): {col.description}")
        return "\n".join(lines)

    def _format_glossary(self, context) -> str:
        """Format the business glossary into a string for the LLM prompt.

        Args:
            context: SemanticContext with business glossary.

        Returns:
            Formatted glossary string mapping terms to definitions.
        """
        lines = []
        for term, definition in context.business_glossary.items():
            lines.append(f"- {term}: {definition}")
        return "\n".join(lines)
