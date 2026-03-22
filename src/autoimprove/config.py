"""Configuration constants for autoimprove.

Directory and file name constants used by the CLI and status command.
The actual config.yaml schema is documented in INSTRUCTIONS.md and
written by the coding agent, not by this tool.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants — directory/file names inside .autoimprove/
# ---------------------------------------------------------------------------

AUTOIMPROVE_DIR = ".autoimprove"
INSTRUCTIONS_FILE = "INSTRUCTIONS.md"
CONFIG_FILE = "config.yaml"
PROGRAM_FILE = "program.md"
EVAL_HARNESS_FILE = "eval_harness.py"
RESULTS_FILE = "results.tsv"
BASELINE_DIR = "baselines"
BASELINE_FILE = "baseline.json"
EXPERIMENTS_DIR = "experiments"
EVALUATORS_DIR = "evaluators"
ANALYSIS_FILE = "analysis.md"
DEFAULT_EXPERIMENT_DURATION = 300  # seconds (5 minutes)


# ---------------------------------------------------------------------------
# Helpers for the status command
# ---------------------------------------------------------------------------


def get_autoimprove_dir(repo_path: str | Path) -> Path:
    """Get the .autoimprove directory for a repo."""
    return Path(repo_path) / AUTOIMPROVE_DIR


def load_baseline(repo_path: str | Path) -> dict[str, Any] | None:
    """Load baseline.json if it exists, else None."""
    path = get_autoimprove_dir(repo_path) / BASELINE_DIR / BASELINE_FILE
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.loads(f.read())
    except (json.JSONDecodeError, OSError):
        return None


def load_config(repo_path: str | Path) -> dict[str, Any] | None:
    """Load config.yaml if it exists, else None.

    Returns a plain dict since the schema is agent-defined.
    """
    try:
        import yaml
    except ImportError:
        return None

    path = get_autoimprove_dir(repo_path) / CONFIG_FILE
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except (OSError, Exception):
        return None
