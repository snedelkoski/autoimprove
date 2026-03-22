"""Configuration models for autoimprove."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AUTOIMPROVE_DIR = ".autoimprove"
CONFIG_FILE = "config.yaml"
PROGRAM_FILE = "program.md"
EVAL_HARNESS_FILE = "eval_harness.py"
RESULTS_FILE = "results.tsv"
BASELINE_DIR = "baselines"
BASELINE_FILE = "baseline.json"
EXPERIMENTS_DIR = "experiments"
EVALUATORS_DIR = "evaluators"


# ---------------------------------------------------------------------------
# LLM settings
# ---------------------------------------------------------------------------

class LLMConfig(BaseModel):
    """LLM provider configuration."""

    model: str = Field(
        default="claude-opus-4-20250514",
        description="Model identifier",
    )
    base_url: str = Field(
        default="https://api.anthropic.com/v1/",
        description="API base URL (OpenAI-compatible endpoint)",
    )
    api_key: str = Field(
        default="",
        description="API key (defaults to OPENAI_API_KEY or ANTHROPIC_API_KEY env var)",
    )
    max_tokens: int = Field(default=4096, description="Max tokens per response")
    temperature: float = Field(default=0.7, description="Sampling temperature")

    def resolve_api_key(self) -> str:
        """Resolve API key from config or environment."""
        if self.api_key:
            return self.api_key
        for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
            val = os.environ.get(var)
            if val:
                return val
        raise ValueError(
            "No API key found. Set ANTHROPIC_API_KEY or OPENAI_API_KEY, "
            "or configure api_key in .autoimprove/config.yaml"
        )

    def resolve_base_url(self) -> str:
        """Resolve base URL from config or environment."""
        env_url = os.environ.get("OPENAI_BASE_URL")
        if env_url:
            return env_url
        return self.base_url


# ---------------------------------------------------------------------------
# Evaluator config
# ---------------------------------------------------------------------------

class EvaluatorConfig(BaseModel):
    """Configuration for a single evaluator."""

    name: str = Field(description="Evaluator name (unique identifier)")
    description: str = Field(default="", description="What this evaluator measures")
    script: str = Field(description="Script filename within evaluators/ directory")
    weight: float = Field(default=1.0, description="Weight in composite score")
    timeout: int = Field(default=300, description="Timeout in seconds")
    enabled: bool = Field(default=True, description="Whether this evaluator is active")


# ---------------------------------------------------------------------------
# Repo analysis results
# ---------------------------------------------------------------------------

class TechStack(BaseModel):
    """Detected technology stack."""

    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    build_system: str = Field(default="")
    package_manager: str = Field(default="")
    test_framework: str = Field(default="")
    test_command: str = Field(default="")
    build_command: str = Field(default="")
    run_command: str = Field(default="")


class FileClassification(BaseModel):
    """Classification of repo files into mutable vs protected."""

    mutable_patterns: list[str] = Field(
        default_factory=list,
        description="Glob patterns for files the agent CAN modify",
    )
    protected_patterns: list[str] = Field(
        default_factory=list,
        description="Glob patterns for files the agent CANNOT modify",
    )


# ---------------------------------------------------------------------------
# Main project config (stored as .autoimprove/config.yaml)
# ---------------------------------------------------------------------------

class ProjectConfig(BaseModel):
    """Full autoimprove configuration for a target repo."""

    version: str = Field(default="0.1.0", description="Config schema version")
    repo_path: str = Field(description="Absolute path to the target repository")
    tech_stack: TechStack = Field(default_factory=TechStack)
    file_classification: FileClassification = Field(default_factory=FileClassification)
    evaluators: list[EvaluatorConfig] = Field(default_factory=list)
    llm: LLMConfig = Field(default_factory=LLMConfig)

    # Experiment settings
    experiment_timeout: int = Field(
        default=600,
        description="Max seconds per experiment (including eval)",
    )
    max_fix_retries: int = Field(
        default=3,
        description="Max retries when an experiment crashes",
    )
    branch_prefix: str = Field(
        default="autoimprove",
        description="Git branch prefix for experiments",
    )

    def save(self, path: Path) -> None:
        """Save config to YAML file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self.model_dump(mode="json")
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    @classmethod
    def load(cls, path: Path) -> "ProjectConfig":
        """Load config from YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_autoimprove_dir(repo_path: str | Path) -> Path:
    """Get the .autoimprove directory for a repo."""
    return Path(repo_path) / AUTOIMPROVE_DIR


def get_config_path(repo_path: str | Path) -> Path:
    """Get the config.yaml path for a repo."""
    return get_autoimprove_dir(repo_path) / CONFIG_FILE


def load_config(repo_path: str | Path) -> ProjectConfig:
    """Load project config, raising if not initialized."""
    config_path = get_config_path(repo_path)
    if not config_path.exists():
        raise FileNotFoundError(
            f"Not an autoimprove repo: {config_path} not found. "
            f"Run 'autoimprove init {repo_path}' first."
        )
    return ProjectConfig.load(config_path)
