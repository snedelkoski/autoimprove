"""Tests for autoimprove CLI module."""

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from autoimprove.cli import main


@pytest.fixture
def runner():
    return CliRunner()


class TestCLI:
    def test_version(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.2.0" in result.output

    def test_help(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "autoimprove" in result.output
        assert "init" in result.output
        assert "status" in result.output

    def test_init_help(self, runner):
        result = runner.invoke(main, ["init", "--help"])
        assert result.exit_code == 0
        assert "Initialize" in result.output
        assert "--force" in result.output
        assert "PATH" in result.output
        # No LLM options should exist
        assert "--model" not in result.output
        assert "--api-key" not in result.output
        assert "--base-url" not in result.output

    def test_status_help(self, runner):
        result = runner.invoke(main, ["status", "--help"])
        assert result.exit_code == 0
        assert "status" in result.output

    def test_no_run_command(self, runner):
        """The 'run' command should not exist in v2."""
        result = runner.invoke(main, ["run", "--help"])
        # Click returns error for unknown commands
        assert result.exit_code != 0


class TestInitCommand:
    @patch("autoimprove.initializer._run_baseline", return_value=None)
    def test_init_basic(self, mock_baseline, runner, tmp_path):
        """Test basic init on a Python project."""
        repo = tmp_path / "test-repo"
        repo.mkdir()
        (repo / "pyproject.toml").write_text(
            '[project]\nname = "test"\ndescription = "Test"\n'
            '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
        )
        (repo / "uv.lock").write_text("# lock")
        (repo / "src").mkdir()
        (repo / "src" / "main.py").write_text("code")
        (repo / "tests").mkdir()
        (repo / "tests" / "test_main.py").write_text("test")

        result = runner.invoke(main, ["init", str(repo)])
        assert result.exit_code == 0
        assert "Initialization complete" in result.output
        assert (repo / ".autoimprove").is_dir()

    @patch("autoimprove.initializer._run_baseline", return_value=None)
    def test_init_force(self, mock_baseline, runner, tmp_path):
        """Test init with --force flag."""
        repo = tmp_path / "test-repo"
        repo.mkdir()
        (repo / "src").mkdir()
        (repo / "src" / "main.py").write_text("code")

        # First init
        runner.invoke(main, ["init", str(repo)])

        # Second init without force should fail
        result = runner.invoke(main, ["init", str(repo)])
        assert result.exit_code != 0
        assert "already exists" in result.output

        # With force should succeed
        result = runner.invoke(main, ["init", str(repo), "--force"])
        assert result.exit_code == 0

    def test_init_nonexistent_path(self, runner):
        """Init on nonexistent path should fail."""
        result = runner.invoke(main, ["init", "/nonexistent/path"])
        assert result.exit_code != 0


class TestStatusCommand:
    def test_status_not_initialized(self, runner, tmp_path):
        """Status on uninitialized repo should fail."""
        result = runner.invoke(main, ["status", str(tmp_path)])
        assert result.exit_code != 0
        assert "Not initialized" in result.output

    @patch("autoimprove.initializer._run_baseline", return_value=None)
    def test_status_after_init(self, mock_baseline, runner, tmp_path):
        """Status after init should show repo info."""
        repo = tmp_path / "test-repo"
        repo.mkdir()
        (repo / "pyproject.toml").write_text(
            '[project]\nname = "test"\ndescription = "A test"\n'
        )
        (repo / "src").mkdir()
        (repo / "src" / "main.py").write_text("code")

        # Initialize
        runner.invoke(main, ["init", str(repo)])

        # Check status
        result = runner.invoke(main, ["status", str(repo)])
        assert result.exit_code == 0
        assert "Repository:" in result.output
        assert "Evaluators:" in result.output
        assert "Experiments:" in result.output
