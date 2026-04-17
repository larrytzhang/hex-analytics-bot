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
from hex.web.session import SessionManager

load_dotenv()
configure_logging()
logger = logging.getLogger(__name__)

# Share one LLMClient + BrainConfig across the default brain and every
# session brain — the client holds the HTTP pool and the config is
# immutable, so there's no reason to instantiate them per-session.
_BRAIN_CONFIG = BrainConfig()
_LLM_CLIENT = LLMClient(_BRAIN_CONFIG)


def _build_orchestrator() -> tuple[AppOrchestrator, SessionManager]:
    """Wire DB → Brain → Viz once at startup and build the session store.

    Mirrors main.py's wiring order minus the Slack gateway. Brain owns DB
    access (per CLAUDE.md §3 Strict Module Boundaries), so the web layer
    only ever sees the orchestrator. The SessionManager is constructed
    here too so the factory it holds captures the same shared LLMClient
    instance as the default brain.
    """
    db = SQLiteEngine()
    if not db.health_check():
        logger.error("Database health check failed — exiting")
        sys.exit(1)

    chart_engine = ChartEngine()
    default_brain = BrainOrchestrator(_BRAIN_CONFIG, db, _LLM_CLIENT)
    logger.info("Web orchestrator wired: model=%s", _BRAIN_CONFIG.model)

    # Each uploaded-CSV session gets its own Brain wired to its own DB.
    # Glossary off — the SaaS glossary (MRR, ARR…) is wrong for arbitrary
    # user schemas and would bias SQL generation.
    def brain_factory(session_db: SQLiteEngine) -> BrainOrchestrator:
        return BrainOrchestrator(
            _BRAIN_CONFIG,
            session_db,
            _LLM_CLIENT,
            use_glossary=False,
        )

    web_config = WebConfig()
    session_manager = SessionManager(
        brain_factory,
        max_sessions=web_config.MAX_SESSIONS,
        ttl_seconds=web_config.SESSION_TTL_SECONDS,
    )

    return AppOrchestrator(default_brain, chart_engine, slack_client=None), session_manager


# Module-level so `uvicorn web_main:app` works for dev hot-reload.
_orchestrator, _session_manager = _build_orchestrator()
app = create_app(_orchestrator, session_manager=_session_manager)


if __name__ == "__main__":
    cfg = WebConfig()
    # Render injects $PORT; honor it transparently so the same image runs
    # locally and in the cloud without env tweaks.
    port = int(os.environ.get("PORT", cfg.PORT))
    uvicorn.run(app, host=cfg.HOST, port=port, log_level="info")
