"""Evaluator utilities — intentionally minimal.

Baseline loading for the `status` command. All evaluation orchestration
is now handled by the agent-written eval_harness.py.
"""

from __future__ import annotations

from autoimprove.config import load_baseline  # re-export for backwards compat

__all__ = ["load_baseline"]
