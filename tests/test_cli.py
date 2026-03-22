"""Tests for the autoimprove CLI."""

import json

import pytest
from click.testing import CliRunner

from autoimprove.cli import main


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def repo(tmp_path):
    """Create a minimal repo for testing."""
    (tmp_path / "README.md").write_text("# Test Project\n")
    (tmp_path / "main.py").write_text("print('hello')\n")
    return tmp_path


class TestMainGroup:
    def test_version(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "autoimprove" in result.output

    def test_help(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "init" in result.output
        assert "status" in result.output

    def test_no_llm_options(self, runner):
        """No LLM options — all intelligence comes from the coding agent."""
        result = runner.invoke(main, ["init", "--help"])
        output = result.output
        assert "--model" not in output
        assert "--api-key" not in output
        assert "--base-url" not in output


class TestInit:
    def test_init_creates_scaffold(self, runner, repo):
        result = runner.invoke(main, ["init", str(repo)])
        assert result.exit_code == 0

        ai_dir = repo / ".autoimprove"
        assert ai_dir.is_dir()
        assert (ai_dir / "INSTRUCTIONS.md").exists()
        assert (ai_dir / "results.tsv").exists()
        assert (ai_dir / "evaluators").is_dir()
        assert (ai_dir / "baselines").is_dir()
        assert (ai_dir / "experiments").is_dir()

    def test_init_instructions_contains_repo_name(self, runner, repo):
        runner.invoke(main, ["init", str(repo)])
        content = (repo / ".autoimprove" / "INSTRUCTIONS.md").read_text()
        assert repo.name in content

    def test_init_instructions_has_key_sections(self, runner, repo):
        runner.invoke(main, ["init", str(repo)])
        content = (repo / ".autoimprove" / "INSTRUCTIONS.md").read_text()
        assert "Phase 1" in content
        assert "Phase 2" in content
        assert "Phase 3" in content
        assert "program.md" in content
        assert "eval_harness" in content
        assert "NEVER STOP" in content

    def test_init_results_tsv_header(self, runner, repo):
        runner.invoke(main, ["init", str(repo)])
        content = (repo / ".autoimprove" / "results.tsv").read_text()
        assert "experiment\tcomposite_score\tstatus\tdescription" in content

    def test_init_only_creates_scaffold(self, runner, repo):
        """init only creates scaffold — agent writes program.md, config, evaluators."""
        runner.invoke(main, ["init", str(repo)])
        ai_dir = repo / ".autoimprove"
        assert not (ai_dir / "program.md").exists()
        assert not (ai_dir / "config.yaml").exists()
        assert not (ai_dir / "eval_harness.py").exists()
        assert len(list((ai_dir / "evaluators").glob("*.py"))) == 0

    def test_init_force_overwrites(self, runner, repo):
        runner.invoke(main, ["init", str(repo)])

        # Second init without --force fails
        result = runner.invoke(main, ["init", str(repo)])
        assert result.exit_code != 0
        assert "already exists" in result.output

        # With --force succeeds
        result = runner.invoke(main, ["init", str(repo), "--force"])
        assert result.exit_code == 0

    def test_init_nonexistent_path(self, runner, tmp_path):
        result = runner.invoke(main, ["init", str(tmp_path / "nope")])
        assert result.exit_code != 0

    def test_init_does_not_modify_repo_files(self, runner, repo):
        main_content = (repo / "main.py").read_text()
        readme_content = (repo / "README.md").read_text()

        runner.invoke(main, ["init", str(repo)])

        assert (repo / "main.py").read_text() == main_content
        assert (repo / "README.md").read_text() == readme_content

    def test_init_output_mentions_instructions(self, runner, repo):
        result = runner.invoke(main, ["init", str(repo)])
        assert "INSTRUCTIONS.md" in result.output

    def test_init_has_duration_option(self, runner):
        result = runner.invoke(main, ["init", "--help"])
        assert "--duration" in result.output

    def test_init_default_duration(self, runner, repo):
        runner.invoke(main, ["init", str(repo)])
        content = (repo / ".autoimprove" / "INSTRUCTIONS.md").read_text()
        assert "experiment_duration_seconds: 300" in content

    def test_init_custom_duration(self, runner, repo):
        runner.invoke(main, ["init", str(repo), "--duration", "600"])
        content = (repo / ".autoimprove" / "INSTRUCTIONS.md").read_text()
        assert "600" in content
        assert "experiment_duration_seconds: 600" in content

    def test_init_instructions_has_primary_metric(self, runner, repo):
        """Instructions must guide agent to identify domain-specific primary metric."""
        runner.invoke(main, ["init", str(repo)])
        content = (repo / ".autoimprove" / "INSTRUCTIONS.md").read_text()
        assert "primary success metric" in content
        assert "Primary Evaluator" in content


class TestStatus:
    def test_status_not_initialized(self, runner, repo):
        result = runner.invoke(main, ["status", str(repo)])
        assert result.exit_code != 0
        assert "Not initialized" in result.output

    def test_status_after_init(self, runner, repo):
        runner.invoke(main, ["init", str(repo)])
        result = runner.invoke(main, ["status", str(repo)])
        assert result.exit_code == 0
        assert "Repository:" in result.output
        assert "Experiments: 0" in result.output

    def test_status_shows_setup_progress(self, runner, repo):
        runner.invoke(main, ["init", str(repo)])
        result = runner.invoke(main, ["status", str(repo)])
        assert "INSTRUCTIONS.md: yes" in result.output
        assert "not yet" in result.output  # program.md doesn't exist yet

    def test_status_shows_baseline_when_present(self, runner, repo):
        runner.invoke(main, ["init", str(repo)])

        # Simulate agent creating baseline
        baseline = {
            "composite_score": 0.75,
            "evaluators": [
                {"name": "test_suite", "score": 1.0, "weight": 3.0},
                {"name": "lint", "score": 0.5, "weight": 1.0},
            ],
        }
        baseline_path = repo / ".autoimprove" / "baselines" / "baseline.json"
        baseline_path.write_text(json.dumps(baseline))

        result = runner.invoke(main, ["status", str(repo)])
        assert "0.750000" in result.output
        assert "test_suite" in result.output
