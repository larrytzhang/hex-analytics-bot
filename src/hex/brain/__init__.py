"""Agentic Brain module.

Re-exports BrainOrchestrator for use exclusively by main.py during
dependency wiring. No other module should import directly from brain/ —
the app orchestrator receives BrainInterface via constructor injection.
"""

from hex.brain.orchestrator import BrainOrchestrator
from hex.brain.config import BrainConfig
from hex.brain.llm_client import LLMClient

__all__ = ["BrainOrchestrator", "BrainConfig", "LLMClient"]
