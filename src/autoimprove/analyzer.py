"""Repository analyzer for autoimprove.

Examines a target repository to detect its tech stack, file structure,
test setup, and classify files into mutable vs protected categories.
Uses an LLM for intelligent classification when heuristics aren't enough.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from autoimprove.config import (
    FileClassification,
    ProjectConfig,
    TechStack,
)
from autoimprove.llm import LLMClient
from autoimprove.prompts import (
    ANALYZE_REPO_SYSTEM,
    ANALYZE_REPO_USER,
    DISCOVER_EVALUATORS_SYSTEM,
    DISCOVER_EVALUATORS_USER,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# File tree scanning
# ---------------------------------------------------------------------------

# Directories to always skip when scanning
SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
    ".eggs", "*.egg-info", ".autoimprove", ".next", ".nuxt", "target",
    "vendor", "coverage", ".coverage", "htmlcov",
}

# Binary / large file extensions to skip reading
SKIP_EXTENSIONS = {
    ".pyc", ".pyo", ".so", ".o", ".a", ".dylib", ".dll", ".exe",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".webp",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".rar", ".7z",
    ".whl", ".egg", ".db", ".sqlite", ".sqlite3",
    ".woff", ".woff2", ".ttf", ".eot",
    ".lock",  # lock files can be huge
    ".min.js", ".min.css",  # minified
}

# Key files to always try to read (if they exist)
KEY_FILES = [
    "README.md", "README.rst", "README.txt", "README",
    "pyproject.toml", "setup.py", "setup.cfg",
    "package.json", "tsconfig.json",
    "Cargo.toml",
    "go.mod", "go.sum",
    "Makefile", "Justfile",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    ".github/workflows/*.yml", ".github/workflows/*.yaml",
    ".gitlab-ci.yml",
    "Gemfile", "build.gradle", "pom.xml",
    "requirements.txt", "Pipfile",
]

# Max chars to read from any single file
MAX_FILE_CHARS = 8000
# Max total chars to send to LLM for analysis
MAX_TOTAL_CHARS = 80000
# Max files to include in the tree
MAX_TREE_FILES = 500


def scan_file_tree(repo_path: Path, max_files: int = MAX_TREE_FILES) -> list[str]:
    """Walk the repo and return a list of relative file paths."""
    files: list[str] = []
    for root, dirs, filenames in os.walk(repo_path):
        # Prune skipped directories
        dirs[:] = [
            d for d in dirs
            if d not in SKIP_DIRS and not d.endswith(".egg-info")
        ]
        for fname in sorted(filenames):
            rel = os.path.relpath(os.path.join(root, fname), repo_path)
            files.append(rel)
            if len(files) >= max_files:
                return files
    return files


def read_key_files(repo_path: Path, file_tree: list[str]) -> dict[str, str]:
    """Read the content of key configuration/documentation files."""
    contents: dict[str, str] = {}
    total_chars = 0

    # First, read explicit key files
    for pattern in KEY_FILES:
        if "*" in pattern:
            # Simple glob
            for fpath in sorted(repo_path.glob(pattern)):
                rel = str(fpath.relative_to(repo_path))
                if rel not in contents and total_chars < MAX_TOTAL_CHARS:
                    try:
                        text = fpath.read_text(errors="replace")[:MAX_FILE_CHARS]
                        contents[rel] = text
                        total_chars += len(text)
                    except (OSError, UnicodeDecodeError):
                        pass
        else:
            fpath = repo_path / pattern
            if fpath.exists() and pattern not in contents and total_chars < MAX_TOTAL_CHARS:
                try:
                    text = fpath.read_text(errors="replace")[:MAX_FILE_CHARS]
                    contents[pattern] = text
                    total_chars += len(text)
                except (OSError, UnicodeDecodeError):
                    pass

    # Then, read a sample of source files to give the LLM context
    source_extensions = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".rb", ".kt"}
    for rel_path in file_tree:
        if total_chars >= MAX_TOTAL_CHARS:
            break
        if rel_path in contents:
            continue
        suffix = Path(rel_path).suffix
        if suffix in source_extensions:
            fpath = repo_path / rel_path
            try:
                text = fpath.read_text(errors="replace")[:MAX_FILE_CHARS]
                contents[rel_path] = text
                total_chars += len(text)
            except (OSError, UnicodeDecodeError):
                pass

    return contents


def format_file_tree(files: list[str]) -> str:
    """Format file list as an indented tree."""
    lines = []
    for f in files:
        depth = f.count(os.sep)
        indent = "  " * depth
        name = os.path.basename(f)
        lines.append(f"{indent}{name}")
    return "\n".join(lines)


def format_file_contents(contents: dict[str, str]) -> str:
    """Format file contents for inclusion in a prompt."""
    parts = []
    for path, content in contents.items():
        parts.append(f"### {path}\n```\n{content}\n```\n")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------

def analyze_repo(repo_path: Path, llm: LLMClient) -> dict[str, Any]:
    """Analyze a repository and return structured analysis.

    Returns a dict with:
    - tech_stack: TechStack
    - file_classification: FileClassification
    - repo_summary: str
    - improvement_areas: list[str]
    """
    logger.info("Scanning file tree at %s", repo_path)
    file_tree = scan_file_tree(repo_path)
    logger.info("Found %d files", len(file_tree))

    logger.info("Reading key files...")
    key_contents = read_key_files(repo_path, file_tree)
    logger.info("Read %d key files (%d total chars)",
                len(key_contents), sum(len(v) for v in key_contents.values()))

    tree_text = format_file_tree(file_tree)
    contents_text = format_file_contents(key_contents)

    logger.info("Sending repo analysis to LLM...")
    user_prompt = ANALYZE_REPO_USER.format(
        file_tree=tree_text,
        file_contents=contents_text,
    )

    analysis = llm.analyze_json(
        ANALYZE_REPO_SYSTEM,
        user_prompt,
        temperature=0.3,
        max_tokens=4096,
    )

    return analysis


def discover_evaluators(
    repo_path: Path,
    analysis: dict[str, Any],
    llm: LLMClient,
) -> list[dict[str, Any]]:
    """Use the LLM to discover custom evaluators for this repo.

    Returns a list of evaluator definitions, each with:
    - name: str
    - description: str
    - weight: float
    - timeout: int
    - script_content: str
    """
    tech = analysis.get("tech_stack", {})
    user_prompt = DISCOVER_EVALUATORS_USER.format(
        repo_analysis=str(analysis),
        languages=", ".join(tech.get("languages", [])),
        frameworks=", ".join(tech.get("frameworks", [])),
        test_framework=tech.get("test_framework", "none"),
        test_command=tech.get("test_command", "none"),
        repo_summary=analysis.get("repo_summary", ""),
    )

    logger.info("Discovering custom evaluators via LLM...")
    evaluators = llm.analyze_json(
        DISCOVER_EVALUATORS_SYSTEM,
        user_prompt,
        temperature=0.5,
        max_tokens=8192,
    )

    # The response should be a list, but handle dict wrapper
    if isinstance(evaluators, dict):
        # Maybe wrapped in {"evaluators": [...]}
        for key in ("evaluators", "results", "scripts"):
            if key in evaluators and isinstance(evaluators[key], list):
                return evaluators[key]
        # Single evaluator dict
        return [evaluators]

    return evaluators
