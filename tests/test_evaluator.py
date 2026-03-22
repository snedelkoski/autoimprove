"""Tests for autoimprove evaluator module."""

import json
from pathlib import Path

import pytest

from autoimprove.evaluator import (
    IMPROVEMENT_EPSILON,
    EvalResult,
    compare_to_baseline,
    load_baseline,
    save_baseline,
)


class TestEvalResult:
    def test_success(self):
        result = EvalResult(
            composite_score=0.85,
            evaluator_results=[{"name": "test", "score": 0.85}],
            elapsed_seconds=5.0,
        )
        assert result.success
        assert result.composite_score == 0.85

    def test_from_crash(self):
        result = EvalResult.from_crash("OOM error")
        assert not result.success
        assert result.error == "OOM error"
        assert result.composite_score == 0.0

    def test_to_dict(self):
        result = EvalResult(
            composite_score=0.9,
            evaluator_results=[],
            elapsed_seconds=1.0,
        )
        d = result.to_dict()
        assert d["composite_score"] == 0.9
        assert d["error"] is None

    def test_summary_success(self):
        result = EvalResult(
            composite_score=0.85,
            evaluator_results=[
                {"name": "tests", "score": 1.0, "weight": 3.0},
                {"name": "complexity", "score": 0.7, "weight": 1.0},
            ],
            elapsed_seconds=5.0,
        )
        summary = result.summary()
        assert "0.850000" in summary
        assert "tests" in summary
        assert "complexity" in summary

    def test_summary_crash(self):
        result = EvalResult.from_crash("segfault")
        assert "CRASH" in result.summary()
        assert "segfault" in result.summary()


class TestCompareToBaseline:
    def test_no_baseline(self):
        result = EvalResult(composite_score=0.5, evaluator_results=[], elapsed_seconds=1.0)
        improved, delta = compare_to_baseline(result, None)
        assert improved is True
        assert delta == 0.5

    def test_improved(self):
        result = EvalResult(composite_score=0.9, evaluator_results=[], elapsed_seconds=1.0)
        baseline = {"composite_score": 0.8}
        improved, delta = compare_to_baseline(result, baseline)
        assert improved is True
        assert abs(delta - 0.1) < 1e-9

    def test_same_score(self):
        result = EvalResult(composite_score=0.8, evaluator_results=[], elapsed_seconds=1.0)
        baseline = {"composite_score": 0.8}
        improved, delta = compare_to_baseline(result, baseline)
        assert improved is False
        assert delta == 0.0

    def test_worse(self):
        result = EvalResult(composite_score=0.7, evaluator_results=[], elapsed_seconds=1.0)
        baseline = {"composite_score": 0.8}
        improved, delta = compare_to_baseline(result, baseline)
        assert improved is False
        assert abs(delta - (-0.1)) < 1e-9

    def test_epsilon_prevents_noise(self):
        """Floating point noise below epsilon should not count as improvement."""
        result = EvalResult(
            composite_score=0.8 + 1e-10,  # tiny floating point noise
            evaluator_results=[],
            elapsed_seconds=1.0,
        )
        baseline = {"composite_score": 0.8}
        improved, delta = compare_to_baseline(result, baseline)
        assert improved is False  # below epsilon threshold

    def test_above_epsilon_counts(self):
        """Improvement above epsilon should count."""
        result = EvalResult(
            composite_score=0.8 + IMPROVEMENT_EPSILON * 2,
            evaluator_results=[],
            elapsed_seconds=1.0,
        )
        baseline = {"composite_score": 0.8}
        improved, delta = compare_to_baseline(result, baseline)
        assert improved is True

    def test_custom_epsilon(self):
        """Custom epsilon threshold should work."""
        result = EvalResult(
            composite_score=0.81,
            evaluator_results=[],
            elapsed_seconds=1.0,
        )
        baseline = {"composite_score": 0.8}
        # With very large epsilon, 0.01 improvement doesn't count
        improved, delta = compare_to_baseline(result, baseline, epsilon=0.05)
        assert improved is False

        # With default epsilon, 0.01 improvement counts
        improved, delta = compare_to_baseline(result, baseline)
        assert improved is True


class TestBaselineIO:
    def test_save_and_load(self, tmp_path):
        ai_dir = tmp_path / ".autoimprove" / "baselines"
        ai_dir.mkdir(parents=True)

        result = EvalResult(
            composite_score=0.85,
            evaluator_results=[{"name": "test", "score": 1.0}],
            elapsed_seconds=3.0,
        )
        save_baseline(tmp_path, result)

        loaded = load_baseline(tmp_path)
        assert loaded is not None
        assert loaded["composite_score"] == 0.85

    def test_load_missing(self, tmp_path):
        loaded = load_baseline(tmp_path)
        assert loaded is None
