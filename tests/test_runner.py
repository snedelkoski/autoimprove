"""Tests for autoimprove runner module (unit tests, no LLM calls)."""

import json
import os
from pathlib import Path

import pytest

from autoimprove.config import FileClassification, ProjectConfig, TechStack
from autoimprove.runner import (
    _is_mutable,
    _log_experiment,
    _read_results_tsv,
    _create_shadow_copies,
    _restore_from_shadow,
)


class TestIsMutable:
    def _config(self, mutable, protected=None):
        return ProjectConfig(
            repo_path="/tmp/test",
            file_classification=FileClassification(
                mutable_patterns=mutable,
                protected_patterns=protected or [],
            ),
        )

    def test_matches_glob(self):
        config = self._config(["src/*.py", "lib/**/*.js"])
        assert _is_mutable("src/main.py", config)

    def test_no_match(self):
        config = self._config(["src/*.py"])
        assert not _is_mutable("tests/test_main.py", config)

    def test_double_star(self):
        config = self._config(["src/**/*.py"])
        # fnmatch doesn't handle ** like glob, but single level works
        assert _is_mutable("src/sub/file.py", config)


class TestLogExperiment:
    def test_appends_to_tsv(self, tmp_path):
        ai_dir = tmp_path / ".autoimprove"
        ai_dir.mkdir()
        results_path = ai_dir / "results.tsv"
        results_path.write_text("experiment\tcomposite_score\tstatus\tdescription\n")

        _log_experiment(tmp_path, "exp_0001", 0.85, "keep", "Test experiment")

        content = results_path.read_text()
        assert "exp_0001" in content
        assert "0.850000" in content
        assert "keep" in content
        assert "Test experiment" in content


class TestReadResultsTsv:
    def test_empty_results(self, tmp_path):
        ai_dir = tmp_path / ".autoimprove"
        ai_dir.mkdir()
        results_path = ai_dir / "results.tsv"
        results_path.write_text("experiment\tcomposite_score\tstatus\tdescription\n")

        result = _read_results_tsv(tmp_path)
        assert "No experiments yet" in result

    def test_with_results(self, tmp_path):
        ai_dir = tmp_path / ".autoimprove"
        ai_dir.mkdir()
        results_path = ai_dir / "results.tsv"
        results_path.write_text(
            "experiment\tcomposite_score\tstatus\tdescription\n"
            "exp_0001\t0.85\tkeep\tTest\n"
        )

        result = _read_results_tsv(tmp_path)
        assert "exp_0001" in result

    def test_missing_file(self, tmp_path):
        result = _read_results_tsv(tmp_path)
        assert "No experiment history" in result


class TestShadowCopies:
    def test_create_and_restore(self, tmp_path):
        # Create a file
        src_file = tmp_path / "src" / "main.py"
        src_file.parent.mkdir(parents=True)
        src_file.write_text("original content")

        # Create .autoimprove/experiments dir
        exp_base = tmp_path / ".autoimprove" / "experiments"
        exp_base.mkdir(parents=True)

        # Shadow copy
        files = [os.path.join("src", "main.py")]
        shadow_dir = _create_shadow_copies(tmp_path, files, "exp_0001")

        # Verify shadow exists
        shadow_file = shadow_dir / "src" / "main.py"
        assert shadow_file.exists()
        assert shadow_file.read_text() == "original content"

        # Modify original
        src_file.write_text("modified content")
        assert src_file.read_text() == "modified content"

        # Restore
        _restore_from_shadow(tmp_path, shadow_dir, files)
        assert src_file.read_text() == "original content"

    def test_restore_removes_new_files(self, tmp_path):
        """If the experiment created a new file, restore should remove it."""
        exp_base = tmp_path / ".autoimprove" / "experiments"
        exp_base.mkdir(parents=True)

        shadow_dir = _create_shadow_copies(tmp_path, ["new_file.py"], "exp_0002")

        # Experiment creates a new file
        new_file = tmp_path / "new_file.py"
        new_file.write_text("new code")

        # Restore should remove it (since it wasn't in shadow)
        _restore_from_shadow(tmp_path, shadow_dir, ["new_file.py"])
        assert not new_file.exists()
