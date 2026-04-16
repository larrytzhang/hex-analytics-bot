"""Web entrypoint for the Hex Analytics Bot.

Mirrors ``main.py`` but skips the Slack gateway: wires DB → Brain → Viz
into an AppOrchestrator (no Slack client), then mounts the FastAPI demo
app on top. Run locally with ``uv run python web_main.py``; in container
deploys (Render, Docker), the same script is the entrypoint.

We deliberately do all wiring at import time so ``uvicorn web_main:app``
also works for hot-reload during development.
"""

from __future__ import annotations

import logging
import os
import sys

import uvicorn
from dotenv import load_dotenv

from hex.app.orchestrator import AppOrchestrator
from hex.brain import BrainConfig, BrainOrchestrator, LLMClient
from hex.db import SQLiteEngine
from hex.shared.logging import configure_logging
from hex.viz import ChartEngine
from hex.web import WebConfig, create_app

load_dotenv()
configure_logging()
logger = logging.getLogger(__name__)


def _build_orchestrator() -> AppOrchestrator:
    """Wire DB → Brain → Viz once at startup.

    Mirrors main.py's wiring order minus the Slack gateway. Brain owns DB
    access (per claude.md §3 Strict Module Boundaries), so the web layer
    only ever sees the orchestrator.
    """
    db = SQLiteEngine()
    if not db.health_check():
        logger.error("Database health check failed — exiting")
        sys.exit(1)

    chart_engine = ChartEngine()
    brain_config = BrainConfig()
    llm_client = LLMClient(brain_config)
    brain = BrainOrchestrator(brain_config, db, llm_client)
    logger.info("Web orchestrator wired: model=%s", brain_config.model)

    return AppOrchestrator(brain, chart_engine, slack_client=None)


# Module-level so `uvicorn web_main:app` works for dev hot-reload.
app = create_app(_build_orchestrator())


if __name__ == "__main__":
    cfg = WebConfig()
    # Render injects $PORT; honor it transparently so the same image runs
    # locally and in the cloud without env tweaks.
    port = int(os.environ.get("PORT", cfg.PORT))
    uvicorn.run(app, host=cfg.HOST, port=port, log_level="info")
