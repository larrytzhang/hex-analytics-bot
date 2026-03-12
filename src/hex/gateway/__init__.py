"""Slack Gateway module.

Re-exports key gateway components for use exclusively by main.py during
dependency wiring. No other module should import directly from gateway/.
"""

from hex.gateway.config import GatewayConfig
from hex.gateway.core.event_listener import SlackEventListener
from hex.gateway.core.request_parser import parse
from hex.gateway.core.response_sender import ResponseSender
from hex.gateway.core.router import Router
from hex.gateway.middleware.dedup import DeduplicationGuard
from hex.gateway.middleware.rate_limiter import RateLimiter

__all__ = [
    "GatewayConfig",
    "SlackEventListener",
    "parse",
    "ResponseSender",
    "Router",
    "DeduplicationGuard",
    "RateLimiter",
]
