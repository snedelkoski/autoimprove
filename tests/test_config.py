"""Tests for autoimprove config module."""

import tempfile
from pathlib import Path

import pytest

from autoimprove.config import (
    AUTOIMPROVE_DIR,
    EvaluatorConfig,
    FileClassification,
    LLMConfig,
    ProjectConfig,
    TechStack,
    get_autoimprove_dir,
    get_config_path,
    load_config,
)


class TestLLMConfig:
    def test_defaults(self):
        config = LLMConfig()
        assert config.model == "claude-opus-4-20250514"
        assert config.temperature == 0.7
        assert config.max_tokens == 4096

    def test_resolve_api_key_from_config(self):
        config = LLMConfig(api_key="test-key")
        assert config.resolve_api_key() == "test-key"

    def test_resolve_api_key_from_env(self, monkeypatch):
        config = LLMConfig()
        monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
        assert config.resolve_api_key() == "env-key"

    def test_resolve_api_key_missing_raises(self, monkeypatch):
        config = LLMConfig()
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(ValueError, match="No API key found"):
            config.resolve_api_key()

    def test_resolve_base_url_default(self, monkeypatch):
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        config = LLMConfig()
        assert config.resolve_base_url() == "https://api.anthropic.com/v1/"

    def test_resolve_base_url_env_override(self, monkeypatch):
        monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
        config = LLMConfig()
        assert config.resolve_base_url() == "http://localhost:11434/v1"


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
