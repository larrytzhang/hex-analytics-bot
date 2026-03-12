"""Slack event listener.

Registers Bolt handlers for app_mention events, ACKs immediately,
and passes events to the router asynchronously. Entry point for
the Slack app in Socket Mode.
"""

import logging

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

from hex.shared.errors import SlackConnectionError

from hex.gateway.core.router import Router

logger = logging.getLogger(__name__)


class SlackEventListener:
    """Listens for Slack events and dispatches them to the router.

    Registers Bolt handlers for app_mention events. ACKs each event
    immediately (within Slack's 3-second window) and processes
    asynchronously via the router.

    Attributes:
        _app:    Slack Bolt AsyncApp instance.
        _router: Router for handling parsed events.
        _handler: Socket Mode handler for WebSocket connection.
    """

    def __init__(self, app: AsyncApp, router: Router, app_token: str) -> None:
        """Initialize the event listener with Slack app and router.

        Registers the app_mention event handler on the Bolt app.

        Args:
            app:       Slack Bolt AsyncApp instance.
            router:    Router for dispatching events.
            app_token: Slack app token for Socket Mode connection.
        """
        self._app = app
        self._router = router
        self._handler = AsyncSocketModeHandler(app, app_token)

        # Register the app_mention handler
        @app.event("app_mention")
        async def handle_app_mention(event, say, body):
            """Handle app_mention events from Slack.

            ACKs immediately by being registered as a Bolt handler.
            Dispatches the raw event body to the router for processing.

            Args:
                event: The Slack event payload.
                say:   Bolt say function (unused — we use the router).
                body:  Full event body including metadata.
            """
            logger.info("Received app_mention from user=%s", event.get("user", "unknown"))
            await self._router.handle(body)

    async def start(self) -> None:
        """Start the Slack event listener in Socket Mode.

        Raises:
            SlackConnectionError: If the initial Slack connection fails.
        """
        try:
            logger.info("Starting Slack event listener (Socket Mode)...")
            await self._handler.start_async()
        except Exception as e:
            logger.error("Failed to connect to Slack: %s", str(e))
            raise SlackConnectionError(f"Failed to connect to Slack: {e}") from e
