"""Tests for the initializer module."""

import pytest

from autoimprove.initializer import initialize_repo


@pytest.fixture
def repo(tmp_path):
    """Create a minimal repo for testing."""
    (tmp_path / "README.md").write_text("# Test Project\n")
    (tmp_path / "main.py").write_text("print('hello')\n")
    return tmp_path


class TestInitializeRepo:
    def test_creates_autoimprove_dir(self, repo):
        initialize_repo(repo)
        assert (repo / ".autoimprove").is_dir()

    def test_creates_subdirectories(self, repo):
        initialize_repo(repo)
        ai_dir = repo / ".autoimprove"
        assert (ai_dir / "evaluators").is_dir()
        assert (ai_dir / "baselines").is_dir()
        assert (ai_dir / "experiments").is_dir()

    def test_creates_instructions(self, repo):
        initialize_repo(repo)
        instructions = repo / ".autoimprove" / "INSTRUCTIONS.md"
        assert instructions.exists()
        content = instructions.read_text()
        assert repo.name in content
        assert "Phase 1" in content
        assert "Phase 2" in content
        assert "Phase 3" in content
        assert "program.md" in content
        assert "NEVER STOP" in content

    def test_creates_instructions_with_default_duration(self, repo):
        initialize_repo(repo)
        content = (repo / ".autoimprove" / "INSTRUCTIONS.md").read_text()
        assert "300" in content
        assert "experiment_duration_seconds: 300" in content

    def test_creates_instructions_with_custom_duration(self, repo):
        initialize_repo(repo, duration=600)
        content = (repo / ".autoimprove" / "INSTRUCTIONS.md").read_text()
        assert "600" in content
        assert "experiment_duration_seconds: 600" in content
        # Should NOT contain the default 300 in the config line
        assert "experiment_duration_seconds: 300" not in content

    def test_creates_results_tsv(self, repo):
        initialize_repo(repo)
        results = repo / ".autoimprove" / "results.tsv"
        assert results.exists()
        content = results.read_text()
        assert content.startswith("experiment\t")

    def test_does_not_create_program_md(self, repo):
        """program.md is agent-written, not CLI-generated."""
        initialize_repo(repo)
        assert not (repo / ".autoimprove" / "program.md").exists()

    def test_does_not_create_config_yaml(self, repo):
        """config.yaml is agent-written, not CLI-generated."""
        initialize_repo(repo)
        assert not (repo / ".autoimprove" / "config.yaml").exists()

    def test_does_not_create_eval_harness(self, repo):
        """eval_harness.py is agent-written, not CLI-generated."""
        initialize_repo(repo)
        assert not (repo / ".autoimprove" / "eval_harness.py").exists()

    def test_does_not_create_evaluator_scripts(self, repo):
        """Evaluator scripts are agent-written, not CLI-generated."""
        initialize_repo(repo)
        evaluators = list((repo / ".autoimprove" / "evaluators").glob("*.py"))
        assert len(evaluators) == 0

    def test_raises_if_exists(self, repo):
        initialize_repo(repo)
        with pytest.raises(FileExistsError, match="already exists"):
            initialize_repo(repo)

    def test_force_overwrites(self, repo):
        initialize_repo(repo)
        initialize_repo(repo, force=True)
        assert (repo / ".autoimprove" / "INSTRUCTIONS.md").exists()

    def test_force_removes_old_files(self, repo):
        """--force should wipe old files that aren't part of the new scaffold."""
        initialize_repo(repo)
        ai_dir = repo / ".autoimprove"
        # Simulate old artifacts that the agent (or previous version) created
        (ai_dir / "program.md").write_text("old program")
        (ai_dir / "config.yaml").write_text("old config")
        (ai_dir / "eval_harness.py").write_text("old harness")
        (ai_dir / "evaluators" / "test_suite.py").write_text("old evaluator")

        initialize_repo(repo, force=True)

        assert not (ai_dir / "program.md").exists()
        assert not (ai_dir / "config.yaml").exists()
        assert not (ai_dir / "eval_harness.py").exists()
        assert len(list((ai_dir / "evaluators").glob("*.py"))) == 0

    def test_raises_for_nonexistent_path(self, tmp_path):
        with pytest.raises(NotADirectoryError):
            initialize_repo(tmp_path / "does_not_exist")

    def test_does_not_modify_repo_files(self, repo):
        main_content = (repo / "main.py").read_text()
        readme_content = (repo / "README.md").read_text()

        initialize_repo(repo)

        assert (repo / "main.py").read_text() == main_content
        assert (repo / "README.md").read_text() == readme_content
