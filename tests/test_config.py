"""Tests for autoimprove config module."""

from pathlib import Path

import pytest

from autoimprove.config import (
    AUTOIMPROVE_DIR,
    EvaluatorConfig,
    FileClassification,
    ProjectConfig,
    TechStack,
    get_autoimprove_dir,
    get_config_path,
    load_config,
)


class TestTechStack:
    def test_defaults(self):
        ts = TechStack()
        assert ts.languages == []
        assert ts.frameworks == []
        assert ts.test_command == ""

    def test_from_dict(self):
        ts = TechStack(
            languages=["python"],
            frameworks=["fastapi"],
            test_command="uv run pytest",
        )
        assert "python" in ts.languages
        assert ts.test_command == "uv run pytest"


class TestFileClassification:
    def test_defaults(self):
        fc = FileClassification()
        assert fc.mutable_patterns == []
        assert fc.protected_patterns == []


class TestEvaluatorConfig:
    def test_defaults(self):
        ec = EvaluatorConfig(name="test_eval", script="test_eval.py")
        assert ec.weight == 1.0
        assert ec.timeout == 300
        assert ec.enabled is True


class TestProjectConfig:
    def test_save_and_load(self, tmp_path):
        config = ProjectConfig(
            repo_path="/tmp/test-repo",
            repo_summary="A test project",
            tech_stack=TechStack(
                languages=["python"],
                test_command="pytest",
            ),
            file_classification=FileClassification(
                mutable_patterns=["src/**/*.py"],
                protected_patterns=["tests/**"],
            ),
            evaluators=[
                EvaluatorConfig(
                    name="complexity",
                    script="complexity.py",
                    weight=1.5,
                ),
            ],
        )

        config_path = tmp_path / "config.yaml"
        config.save(config_path)

        assert config_path.exists()

        loaded = ProjectConfig.load(config_path)
        assert loaded.repo_path == "/tmp/test-repo"
        assert loaded.repo_summary == "A test project"
        assert loaded.tech_stack.languages == ["python"]
        assert loaded.tech_stack.test_command == "pytest"
        assert len(loaded.evaluators) == 1
        assert loaded.evaluators[0].name == "complexity"
        assert loaded.evaluators[0].weight == 1.5

    def test_save_creates_parent_dirs(self, tmp_path):
        config = ProjectConfig(repo_path="/tmp/test")
        config_path = tmp_path / "deep" / "nested" / "config.yaml"
        config.save(config_path)
        assert config_path.exists()

    def test_version_defaults_to_0_2_0(self):
        config = ProjectConfig(repo_path="/tmp/test")
        assert config.version == "0.2.0"

    def test_no_llm_config(self):
        """Verify LLMConfig is no longer part of ProjectConfig."""
        config = ProjectConfig(repo_path="/tmp/test")
        assert not hasattr(config, "llm")


class TestHelpers:
    def test_get_autoimprove_dir(self):
        result = get_autoimprove_dir("/tmp/test-repo")
        assert result == Path("/tmp/test-repo/.autoimprove")

    def test_get_config_path(self):
        result = get_config_path("/tmp/test-repo")
        assert result == Path("/tmp/test-repo/.autoimprove/config.yaml")

    def test_load_config_missing_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Not an autoimprove repo"):
            load_config(tmp_path)
