"""Application entrypoint for the Hex Agentic Analytics Slack Bot.

Initializes all modules, wires dependencies, validates startup
conditions, and starts the Slack event listener in Socket Mode.
"""

import asyncio
import logging
import sys

from dotenv import load_dotenv

from hex.shared.logging import configure_logging
from hex.shared.errors import SlackConnectionError


async def main() -> None:
    """Initialize all components and start the Slack bot.

    Dependency wiring order:
    1. Load environment and configure logging
    2. Instantiate SQLiteEngine (auto-seeds)
    3. Validate DB health
    4. Instantiate ChartEngine
    5. Instantiate LLMClient + BrainOrchestrator (inject db + llm)
    6. Instantiate AppOrchestrator (inject brain + chart + slack)
    7. Instantiate Gateway components (inject orchestrator)
    8. Start Slack event listener
    """
    # Step 1: Environment and logging
    load_dotenv()
    configure_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting Hex Analytics Bot...")

    # Step 2: Database engine
    from hex.db import SQLiteEngine
    db = SQLiteEngine()

    # Step 3: Health check
    if not db.health_check():
        logger.error("Database health check failed — exiting")
        sys.exit(1)
    logger.info("Database initialized and healthy")

    # Step 4: Chart engine
    from hex.viz import ChartEngine
    chart_engine = ChartEngine()
    logger.info("Chart engine initialized")

    # Step 5: Brain
    from hex.brain import BrainConfig, LLMClient, BrainOrchestrator
    brain_config = BrainConfig()
    llm_client = LLMClient(brain_config)
    brain = BrainOrchestrator(brain_config, db, llm_client)
    logger.info("Brain initialized with model=%s", brain_config.model)

    # Step 6: Slack client and App Orchestrator
    from slack_sdk.web.async_client import AsyncWebClient
    from hex.gateway import GatewayConfig
    gateway_config = GatewayConfig()

    slack_client = AsyncWebClient(token=gateway_config.SLACK_BOT_TOKEN)

    from hex.app.orchestrator import AppOrchestrator
    orchestrator = AppOrchestrator(brain, chart_engine, slack_client)
    logger.info("App orchestrator initialized")

    # Step 7: Gateway components
    from hex.gateway import DeduplicationGuard, RateLimiter, ResponseSender, Router, SlackEventListener
    from slack_bolt.async_app import AsyncApp

    bolt_app = AsyncApp(token=gateway_config.SLACK_BOT_TOKEN)
    dedup = DeduplicationGuard(ttl_seconds=gateway_config.DEDUP_TTL_SECONDS)
    rate_limiter = RateLimiter(max_retries=gateway_config.RATE_LIMIT_MAX_RETRIES)
    sender = ResponseSender(slack_client, rate_limiter)
    router = Router(
        orchestrator=orchestrator,
        sender=sender,
        dedup=dedup,
        slack_client=slack_client,
        timeout=gateway_config.BRAIN_TIMEOUT_SECONDS,
    )
    listener = SlackEventListener(bolt_app, router, gateway_config.SLACK_APP_TOKEN)
    logger.info("Gateway components initialized")

    # Step 8: Start
    try:
        logger.info("Slack bot is running! Waiting for events...")
        await listener.start()
    except SlackConnectionError as e:
        logger.error("Failed to connect to Slack: %s", str(e))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
