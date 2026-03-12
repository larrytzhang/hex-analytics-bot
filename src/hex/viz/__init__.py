"""Visualization engine module.

Re-exports ChartEngine for use exclusively by main.py during dependency wiring.
No other module should import directly from viz/ — the orchestrator receives
ChartEngineInterface via constructor injection.
"""

from hex.viz.engine import ChartEngine

__all__ = ["ChartEngine"]
