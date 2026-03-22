"""Evaluation orchestration for autoimprove.

Runs the eval harness, parses results, and compares against baselines.
This module is used by the runner during the improvement loop.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from autoimprove.config import (
    AUTOIMPROVE_DIR,
    BASELINE_DIR,
    BASELINE_FILE,
    EVAL_HARNESS_FILE,
    ProjectConfig,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

class EvalResult:
    """Result from running the evaluation harness."""

    def __init__(
        self,
        composite_score: float,
        evaluator_results: list[dict[str, Any]],
        elapsed_seconds: float,
        raw_output: str = "",
        error: str | None = None,
    ):
        self.composite_score = composite_score
        self.evaluator_results = evaluator_results
        self.elapsed_seconds = elapsed_seconds
        self.raw_output = raw_output
        self.error = error

    @property
    def success(self) -> bool:
        return self.error is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "composite_score": self.composite_score,
            "evaluator_results": self.evaluator_results,
            "elapsed_seconds": self.elapsed_seconds,
            "error": self.error,
        }

    @classmethod
    def from_crash(cls, error: str) -> "EvalResult":
        """Create a result representing a crashed evaluation."""
        return cls(
            composite_score=0.0,
            evaluator_results=[],
            elapsed_seconds=0.0,
            error=error,
        )

    def summary(self) -> str:
        """Human-readable summary of the evaluation."""
        if not self.success:
            return f"CRASH: {self.error}"
        lines = [f"Composite score: {self.composite_score:.6f}"]
        for er in self.evaluator_results:
            name = er.get("name", "unknown")
            score = er.get("score", 0.0)
            weight = er.get("weight", 1.0)
            lines.append(f"  {name}: {score:.4f} (weight={weight})")
        lines.append(f"  Elapsed: {self.elapsed_seconds:.1f}s")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Running evaluation
# ---------------------------------------------------------------------------

def run_evaluation(repo_path: Path, config: ProjectConfig) -> EvalResult:
    """Run the full evaluation harness and return results.

    Args:
        repo_path: Path to the target repository root.
        config: The project configuration.

    Returns:
        EvalResult with composite score and per-evaluator scores.
    """
    ai_dir = repo_path / AUTOIMPROVE_DIR
    harness_path = ai_dir / EVAL_HARNESS_FILE

    if not harness_path.exists():
        return EvalResult.from_crash(f"Eval harness not found: {harness_path}")

    timeout = config.experiment_timeout

    try:
        result = subprocess.run(
            ["uv", "run", str(harness_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(repo_path),
        )
    except subprocess.TimeoutExpired:
        return EvalResult.from_crash(f"Evaluation timed out after {timeout}s")
    except FileNotFoundError:
        return EvalResult.from_crash("uv not found. Install uv: https://docs.astral.sh/uv/")

    if result.returncode != 0:
        stderr_tail = result.stderr[-500:] if result.stderr else ""
        return EvalResult.from_crash(
            f"Eval harness exited with code {result.returncode}: {stderr_tail}"
        )

    # Parse JSON output
    stdout = result.stdout.strip()
    if not stdout:
        return EvalResult.from_crash("Eval harness produced no output")

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as e:
        return EvalResult.from_crash(f"Eval harness output is not valid JSON: {e}")

    return EvalResult(
        composite_score=data.get("composite_score", 0.0),
        evaluator_results=data.get("evaluators", []),
        elapsed_seconds=data.get("elapsed_seconds", 0.0),
        raw_output=stdout,
    )


# ---------------------------------------------------------------------------
# Baseline management
# ---------------------------------------------------------------------------

def load_baseline(repo_path: Path) -> dict[str, Any] | None:
    """Load the baseline metrics from disk."""
    baseline_path = repo_path / AUTOIMPROVE_DIR / BASELINE_DIR / BASELINE_FILE
    if not baseline_path.exists():
        return None
    try:
        with open(baseline_path) as f:
            return json.loads(f.read())
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load baseline: %s", e)
        return None


def save_baseline(repo_path: Path, result: EvalResult) -> None:
    """Save current evaluation result as the new baseline."""
    baseline_path = repo_path / AUTOIMPROVE_DIR / BASELINE_DIR / BASELINE_FILE
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    data = result.to_dict()
    baseline_path.write_text(json.dumps(data, indent=2))
    logger.info("Updated baseline: composite_score=%.6f", result.composite_score)


def compare_to_baseline(
    result: EvalResult,
    baseline: dict[str, Any] | None,
) -> tuple[bool, float]:
    """Compare evaluation result to baseline.

    Returns:
        (improved, delta) where improved is True if the composite score
        is strictly better (higher) than baseline, and delta is the difference.
    """
    if baseline is None:
        # No baseline — first run is always "improved"
        return True, result.composite_score

    baseline_score = baseline.get("composite_score", 0.0)
    delta = result.composite_score - baseline_score

    # Strictly improved (even tiny improvements count)
    improved = delta > 0

    return improved, delta
