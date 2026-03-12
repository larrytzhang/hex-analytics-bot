"""Slack event router.

Orchestrates the full event handling flow: dedup -> parse -> add
thinking reaction -> call orchestrator -> send response -> remove
thinking reaction. Handles errors with user-friendly fallbacks.
"""

import asyncio
import logging

from hex.shared.errors import DuplicateEventError, EventValidationError
from hex.shared.interfaces import OrchestratorInterface
from hex.shared.models import ResponseType, SlackResponse

from hex.gateway.core.request_parser import parse
from hex.gateway.core.response_sender import ResponseSender
from hex.gateway.middleware.dedup import DeduplicationGuard

logger = logging.getLogger(__name__)


class Router:
    """Routes incoming Slack events through the processing pipeline.

    Flow: dedup check -> parse event -> add thinking reaction ->
    call orchestrator -> send response -> remove thinking reaction.

    Attributes:
        _orchestrator:  OrchestratorInterface for question handling.
        _sender:        ResponseSender for delivering responses.
        _dedup:         DeduplicationGuard for idempotency.
        _slack_client:  Slack AsyncWebClient for reaction APIs.
        _timeout:       Timeout in seconds for the orchestrator call.
    """

    def __init__(
        self,
        orchestrator: OrchestratorInterface,
        sender: ResponseSender,
        dedup: DeduplicationGuard,
        slack_client,
        timeout: int = 30,
    ) -> None:
        """Initialize the router with all dependencies.

        Args:
            orchestrator: The app orchestrator for handling questions.
            sender:       ResponseSender for delivering responses.
            dedup:        DeduplicationGuard for event deduplication.
            slack_client: Slack AsyncWebClient for reactions.
            timeout:      Timeout seconds for orchestrator calls (default 30).
        """
        self._orchestrator = orchestrator
        self._sender = sender
        self._dedup = dedup
        self._slack_client = slack_client
        self._timeout = timeout

    async def handle(self, raw_event: dict) -> None:
        """Handle a raw Slack event through the full pipeline.

        Args:
            raw_event: Raw event dict from the Slack event API.
        """
        # Step 1: Dedup check
        event = raw_event.get("event", raw_event)
        event_id = raw_event.get("event_id", event.get("client_msg_id", ""))
        try:
            self._dedup.check(event_id)
        except DuplicateEventError:
            logger.debug("Duplicate event %s — silently ignoring", event_id)
            return

        # Step 2: Parse event
        try:
            request = parse(raw_event)
        except EventValidationError as e:
            logger.warning("Event validation failed: %s", str(e))
            return

        # Step 3: Add thinking reaction
        try:
            await self._slack_client.reactions_add(
                channel=request.channel_id,
                timestamp=request.message_ts,
                name="thinking_face",
            )
        except Exception:
            pass  # Reaction failure is non-critical

        try:
            # Step 4: Call orchestrator with timeout
            response = await asyncio.wait_for(
                self._orchestrator.handle_question(request),
                timeout=self._timeout,
            )

            # Step 5: Send response
            await self._sender.send(response)

        except asyncio.TimeoutError:
            logger.warning("Orchestrator timeout for event %s", event_id)
            error_response = SlackResponse(
                channel_id=request.channel_id,
                thread_ts=request.thread_ts,
                response_type=ResponseType.TEXT,
                text="Sorry, that took too long. Please try again or simplify your question.",
            )
            await self._sender.send(error_response)

        except Exception as e:
            logger.error("Unexpected error handling event %s: %s", event_id, str(e))
            error_response = SlackResponse(
                channel_id=request.channel_id,
                thread_ts=request.thread_ts,
                response_type=ResponseType.TEXT,
                text="Something went wrong while processing your question. Please try again.",
            )
            try:
                await self._sender.send(error_response)
            except Exception:
                logger.error("Failed to send error response for event %s", event_id)

        finally:
            # Step 6: Remove thinking reaction
            try:
                await self._slack_client.reactions_remove(
                    channel=request.channel_id,
                    timestamp=request.message_ts,
                    name="thinking_face",
                )
            except Exception:
                pass  # Reaction removal failure is non-critical
