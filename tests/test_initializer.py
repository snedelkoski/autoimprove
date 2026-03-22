"""Tests for autoimprove initializer module."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from autoimprove.config import (
    AUTOIMPROVE_DIR,
    BASELINE_DIR,
    BASELINE_FILE,
    CONFIG_FILE,
    EVAL_HARNESS_FILE,
    EVALUATORS_DIR,
    EXPERIMENTS_DIR,
    PROGRAM_FILE,
    RESULTS_FILE,
    ProjectConfig,
)
from autoimprove.initializer import initialize_repo


def _create_python_repo(tmp_path: Path) -> Path:
    """Create a minimal Python repo for testing."""
    repo = tmp_path / "my-project"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "my-project"\n'
        'description = "A test project"\n'
        'dependencies = ["fastapi"]\n\n'
        '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
    )
    (repo / "uv.lock").write_text("# lock")
    (repo / "src").mkdir()
    (repo / "src" / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n")
    (repo / "src" / "utils.py").write_text("def helper(): pass\n")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_main.py").write_text("def test_app(): pass\n")
    (repo / "README.md").write_text("# My Project\nA test project.\n")
    return repo


class TestInitializeRepo:
    @patch("autoimprove.initializer._run_baseline", return_value=None)
    def test_creates_directory_structure(self, mock_baseline, tmp_path):
        """Init should create .autoimprove/ with all subdirectories."""
        repo = _create_python_repo(tmp_path)
        initialize_repo(repo)

        ai_dir = repo / AUTOIMPROVE_DIR
        assert ai_dir.is_dir()
        assert (ai_dir / EVALUATORS_DIR).is_dir()
        assert (ai_dir / EXPERIMENTS_DIR).is_dir()
        assert (ai_dir / BASELINE_DIR).is_dir()

    @patch("autoimprove.initializer._run_baseline", return_value=None)
    def test_creates_config_yaml(self, mock_baseline, tmp_path):
        """Init should create a valid config.yaml."""
        repo = _create_python_repo(tmp_path)
        config = initialize_repo(repo)

        config_path = repo / AUTOIMPROVE_DIR / CONFIG_FILE
        assert config_path.exists()

        loaded = ProjectConfig.load(config_path)
        assert loaded.repo_path == str(repo)
        assert "python" in loaded.tech_stack.languages
        assert loaded.tech_stack.package_manager == "uv"
        assert "uv run pytest" in loaded.tech_stack.test_command
        assert len(loaded.evaluators) > 0

    @patch("autoimprove.initializer._run_baseline", return_value=None)
    def test_creates_program_md(self, mock_baseline, tmp_path):
        """Init should create a well-formed program.md."""
        repo = _create_python_repo(tmp_path)
        initialize_repo(repo)

        program_path = repo / AUTOIMPROVE_DIR / PROGRAM_FILE
        assert program_path.exists()

        content = program_path.read_text()
        assert "autoimprove" in content
        assert "my-project" in content
        assert "python" in content.lower()
        assert "eval_harness.py" in content
        assert "LOOP FOREVER" in content
        assert "NEVER STOP" in content

    @patch("autoimprove.initializer._run_baseline", return_value=None)
    def test_creates_eval_harness(self, mock_baseline, tmp_path):
        """Init should create eval_harness.py."""
        repo = _create_python_repo(tmp_path)
        initialize_repo(repo)

        harness_path = repo / AUTOIMPROVE_DIR / EVAL_HARNESS_FILE
        assert harness_path.exists()

        content = harness_path.read_text()
        assert "#!/usr/bin/env python3" in content
        assert "composite_score" in content
        assert "uv run" in content

    @patch("autoimprove.initializer._run_baseline", return_value=None)
    def test_creates_evaluator_scripts(self, mock_baseline, tmp_path):
        """Init should create evaluator scripts in evaluators/ directory."""
        repo = _create_python_repo(tmp_path)
        initialize_repo(repo)

        evaluators_dir = repo / AUTOIMPROVE_DIR / EVALUATORS_DIR
        scripts = list(evaluators_dir.glob("*.py"))
        # Python project should have at least complexity + type_coverage + lint
        assert len(scripts) >= 3

        # Each script should be valid Python with PEP 723 metadata
        for script in scripts:
            content = script.read_text()
            assert "#!/usr/bin/env python3" in content
            assert "# /// script" in content
            assert "json.dumps" in content

    @patch("autoimprove.initializer._run_baseline", return_value=None)
    def test_creates_results_tsv(self, mock_baseline, tmp_path):
        """Init should create results.tsv with header."""
        repo = _create_python_repo(tmp_path)
        initialize_repo(repo)

        results_path = repo / AUTOIMPROVE_DIR / RESULTS_FILE
        assert results_path.exists()
        content = results_path.read_text()
        assert "experiment\t" in content
        assert "composite_score\t" in content

    @patch("autoimprove.initializer._run_baseline", return_value=None)
    def test_force_overwrites(self, mock_baseline, tmp_path):
        """Init with --force should overwrite existing .autoimprove/."""
        repo = _create_python_repo(tmp_path)

        # First init
        initialize_repo(repo)

        # Second init without force should fail
        with pytest.raises(FileExistsError):
            initialize_repo(repo)

        # With force should succeed
        initialize_repo(repo, force=True)

    @patch("autoimprove.initializer._run_baseline", return_value=None)
    def test_does_not_modify_repo_files(self, mock_baseline, tmp_path):
        """Init should only add .autoimprove/, never modify existing files."""
        repo = _create_python_repo(tmp_path)

        # Record original file contents
        original_files = {}
        for fpath in repo.rglob("*"):
            if fpath.is_file():
                original_files[str(fpath.relative_to(repo))] = fpath.read_text()

        initialize_repo(repo)

        # Verify original files are unchanged
        for rel_path, original_content in original_files.items():
            fpath = repo / rel_path
            assert fpath.exists(), f"Original file deleted: {rel_path}"
            assert fpath.read_text() == original_content, f"File modified: {rel_path}"

    def test_not_a_directory_raises(self, tmp_path):
        """Init on a non-directory should raise."""
        fpath = tmp_path / "file.txt"
        fpath.write_text("not a dir")
        with pytest.raises(NotADirectoryError):
            initialize_repo(fpath)

    @patch("autoimprove.initializer._run_baseline")
    def test_baseline_saved_on_success(self, mock_baseline, tmp_path):
        """If baseline eval succeeds, it should be saved."""
        mock_baseline.return_value = {
            "composite_score": 0.85,
            "evaluators": [{"name": "test", "score": 1.0}],
        }
        repo = _create_python_repo(tmp_path)
        initialize_repo(repo)

        baseline_path = repo / AUTOIMPROVE_DIR / BASELINE_DIR / BASELINE_FILE
        assert baseline_path.exists()
        data = json.loads(baseline_path.read_text())
        assert data["composite_score"] == 0.85

    @patch("autoimprove.initializer._run_baseline", return_value=None)
    def test_returns_project_config(self, mock_baseline, tmp_path):
        """Init should return a valid ProjectConfig."""
        repo = _create_python_repo(tmp_path)
        config = initialize_repo(repo)

        assert isinstance(config, ProjectConfig)
        assert config.repo_path == str(repo)
        assert "python" in config.tech_stack.languages
        assert len(config.evaluators) > 0
        assert len(config.file_classification.mutable_patterns) > 0
