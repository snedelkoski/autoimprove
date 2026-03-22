"""Tests for autoimprove config module."""

import json
from pathlib import Path

import pytest

from autoimprove.config import (
    AUTOIMPROVE_DIR,
    BASELINE_DIR,
    BASELINE_FILE,
    CONFIG_FILE,
    EVAL_HARNESS_FILE,
    EVALUATORS_DIR,
    EXPERIMENTS_DIR,
    INSTRUCTIONS_FILE,
    PROGRAM_FILE,
    RESULTS_FILE,
    get_autoimprove_dir,
    load_baseline,
    load_config,
)


class TestConstants:
    def test_autoimprove_dir(self):
        assert AUTOIMPROVE_DIR == ".autoimprove"

    def test_instructions_file(self):
        assert INSTRUCTIONS_FILE == "INSTRUCTIONS.md"

    def test_config_file(self):
        assert CONFIG_FILE == "config.yaml"

    def test_program_file(self):
        assert PROGRAM_FILE == "program.md"

    def test_results_file(self):
        assert RESULTS_FILE == "results.tsv"


class TestGetAutoimproveDir:
    def test_from_string(self):
        result = get_autoimprove_dir("/some/repo")
        assert result == Path("/some/repo/.autoimprove")

    def test_from_path(self):
        result = get_autoimprove_dir(Path("/some/repo"))
        assert result == Path("/some/repo/.autoimprove")


class TestLoadBaseline:
    def test_missing_returns_none(self, tmp_path):
        assert load_baseline(tmp_path) is None

    def test_valid_json(self, tmp_path):
        baseline_dir = tmp_path / ".autoimprove" / "baselines"
        baseline_dir.mkdir(parents=True)
        data = {"composite_score": 0.85, "evaluators": []}
        (baseline_dir / "baseline.json").write_text(json.dumps(data))

        result = load_baseline(tmp_path)
        assert result is not None
        assert result["composite_score"] == 0.85

    def test_invalid_json_returns_none(self, tmp_path):
        baseline_dir = tmp_path / ".autoimprove" / "baselines"
        baseline_dir.mkdir(parents=True)
        (baseline_dir / "baseline.json").write_text("not json")

        assert load_baseline(tmp_path) is None


class TestLoadConfig:
    def test_missing_returns_none(self, tmp_path):
        assert load_config(tmp_path) is None

    def test_valid_yaml(self, tmp_path):
        config_dir = tmp_path / ".autoimprove"
        config_dir.mkdir(parents=True)
        (config_dir / "config.yaml").write_text(
            "version: '1.0'\nrepo: test\nsummary: a test project\n"
        )

        result = load_config(tmp_path)
        assert result is not None
        assert result["version"] == "1.0"
        assert result["repo"] == "test"
