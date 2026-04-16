"""Web I/O surface for the Hex Analytics Bot.

Public exports for the web module. Like ``gateway/``, this is an
adapter — it takes HTTP requests, calls AppOrchestrator.compute_answer,
and renders an HTTP response. It does not import from any peer
module's internals.
"""

from hex.web.config import WebConfig
from hex.web.server import create_app

__all__ = ["WebConfig", "create_app"]
