"""Tests for autoimprove analyzer module."""

import json
import os
from pathlib import Path

import pytest

from autoimprove.analyzer import (
    SKIP_DIRS,
    classify_files,
    detect_tech_stack,
    discover_evaluators,
    format_file_contents,
    format_file_tree,
    read_key_files,
    scan_file_tree,
)
from autoimprove.config import TechStack


# ---------------------------------------------------------------------------
# File tree scanning tests (carried over from v1)
# ---------------------------------------------------------------------------

class TestScanFileTree:
    def test_basic_scan(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("print('hello')")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_main.py").write_text("def test(): pass")
        (tmp_path / "README.md").write_text("# Hello")

        files = scan_file_tree(tmp_path)
        assert len(files) == 3
        assert "README.md" in files
        assert os.path.join("src", "main.py") in files
        assert os.path.join("tests", "test_main.py") in files

    def test_skips_hidden_dirs(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("stuff")
        (tmp_path / "main.py").write_text("code")

        files = scan_file_tree(tmp_path)
        assert len(files) == 1
        assert "main.py" in files

    def test_skips_node_modules(self, tmp_path):
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "pkg").mkdir()
        (tmp_path / "node_modules" / "pkg" / "index.js").write_text("code")
        (tmp_path / "index.js").write_text("code")

        files = scan_file_tree(tmp_path)
        assert len(files) == 1
        assert "index.js" in files

    def test_max_files_limit(self, tmp_path):
        for i in range(20):
            (tmp_path / f"file_{i}.txt").write_text("x")

        files = scan_file_tree(tmp_path, max_files=5)
        assert len(files) == 5


class TestReadKeyFiles:
    def test_reads_readme(self, tmp_path):
        (tmp_path / "README.md").write_text("# My Project")
        file_tree = ["README.md"]

        contents = read_key_files(tmp_path, file_tree)
        assert "README.md" in contents
        assert "# My Project" in contents["README.md"]

    def test_reads_pyproject(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"')
        file_tree = ["pyproject.toml"]

        contents = read_key_files(tmp_path, file_tree)
        assert "pyproject.toml" in contents

    def test_reads_source_files(self, tmp_path):
        (tmp_path / "app.py").write_text("def main(): pass")
        file_tree = ["app.py"]

        contents = read_key_files(tmp_path, file_tree)
        assert "app.py" in contents


class TestFormatFileTree:
    def test_simple_tree(self):
        files = ["README.md", "src/main.py", "src/utils.py"]
        result = format_file_tree(files)
        assert "README.md" in result
        assert "main.py" in result
        assert "utils.py" in result


class TestFormatFileContents:
    def test_formatting(self):
        contents = {"main.py": "print('hello')"}
        result = format_file_contents(contents)
        assert "### main.py" in result
        assert "print('hello')" in result
        assert "```" in result


# ---------------------------------------------------------------------------
# Tech stack detection tests (new for v2)
# ---------------------------------------------------------------------------

class TestDetectTechStack:
    def test_python_uv_project(self, tmp_path):
        """Detect a Python project using uv with pytest."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\ndescription = "My app"\n'
            'dependencies = ["fastapi"]\n\n'
            '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
        )
        (tmp_path / "uv.lock").write_text("# lock")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("import fastapi")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_main.py").write_text("def test(): pass")

        tech_stack, summary = detect_tech_stack(tmp_path)

        assert "python" in tech_stack.languages
        assert "fastapi" in tech_stack.frameworks
        assert tech_stack.package_manager == "uv"
        assert tech_stack.test_framework == "pytest"
        assert "uv run pytest" in tech_stack.test_command
        assert "My app" in summary

    def test_node_project(self, tmp_path):
        """Detect a Node.js/TypeScript project."""
        pkg = {
            "name": "my-app",
            "description": "A React app",
            "scripts": {"test": "vitest run", "build": "vite build", "dev": "vite dev"},
            "dependencies": {"react": "^18.0.0"},
            "devDependencies": {"vitest": "^1.0.0", "vite": "^5.0.0", "typescript": "^5.0.0"},
        }
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        (tmp_path / "pnpm-lock.yaml").write_text("# lock")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "App.tsx").write_text("export default function App() {}")

        tech_stack, summary = detect_tech_stack(tmp_path)

        assert "typescript" in tech_stack.languages
        assert "react" in tech_stack.frameworks
        assert tech_stack.package_manager == "pnpm"
        assert tech_stack.test_framework == "vitest"
        assert "A React app" in summary

    def test_rust_project(self, tmp_path):
        """Detect a Rust project."""
        (tmp_path / "Cargo.toml").write_text(
            '[package]\nname = "myapp"\ndescription = "A Rust app"\n\n'
            '[dependencies]\naxum = "0.7"\ntokio = { version = "1", features = ["full"] }\n'
        )
        (tmp_path / "Cargo.lock").write_text("# lock")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.rs").write_text("fn main() {}")

        tech_stack, summary = detect_tech_stack(tmp_path)

        assert "rust" in tech_stack.languages
        assert "axum" in tech_stack.frameworks
        assert "tokio" in tech_stack.frameworks
        assert tech_stack.package_manager == "cargo"
        assert tech_stack.test_framework == "cargo test"
        assert tech_stack.test_command == "cargo test"
        assert "A Rust app" in summary

    def test_go_project(self, tmp_path):
        """Detect a Go project."""
        (tmp_path / "go.mod").write_text(
            "module github.com/user/myapp\n\n"
            "go 1.21\n\n"
            "require github.com/gin-gonic/gin v1.9.0\n"
        )
        (tmp_path / "go.sum").write_text("# sums")
        (tmp_path / "cmd").mkdir()
        (tmp_path / "cmd" / "main.go").write_text("package main")
        (tmp_path / "internal").mkdir()
        (tmp_path / "internal" / "handler.go").write_text("package internal")

        tech_stack, summary = detect_tech_stack(tmp_path)

        assert "go" in tech_stack.languages
        assert "gin" in tech_stack.frameworks
        assert tech_stack.package_manager == "go"
        assert tech_stack.test_command == "go test ./..."

    def test_empty_repo(self, tmp_path):
        """Handle a completely empty directory."""
        tech_stack, summary = detect_tech_stack(tmp_path)

        assert tech_stack.languages == []
        assert tech_stack.frameworks == []
        assert tech_stack.package_manager == ""
        assert tech_stack.test_command == ""

    def test_makefile_test_target(self, tmp_path):
        """Detect test command from Makefile."""
        (tmp_path / "Makefile").write_text(
            ".PHONY: test build\n\n"
            "test:\n\tpytest tests/\n\n"
            "build:\n\tpython -m build\n"
        )
        (tmp_path / "main.py").write_text("print('hello')")

        tech_stack, _ = detect_tech_stack(tmp_path)

        assert tech_stack.build_system == "make"
        # Should detect make test from Makefile
        assert tech_stack.test_command == "make test"


# ---------------------------------------------------------------------------
# File classification tests (new for v2)
# ---------------------------------------------------------------------------

class TestClassifyFiles:
    def test_python_project(self, tmp_path):
        """Classify files in a Python project."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("code")
        (tmp_path / "src" / "utils.py").write_text("code")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_app.py").write_text("test")
        (tmp_path / "pyproject.toml").write_text('[project]\nname="x"')
        (tmp_path / "README.md").write_text("# readme")

        tech_stack = TechStack(languages=["python"])
        classification = classify_files(tmp_path, tech_stack)

        # src/**/*.py should be mutable
        assert any("src" in p and ".py" in p for p in classification.mutable_patterns)
        # tests should be protected
        assert any("tests" in p for p in classification.protected_patterns)
        # README should be protected
        assert any("README" in p for p in classification.protected_patterns)

    def test_node_project(self, tmp_path):
        """Classify files in a Node.js project."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "index.ts").write_text("code")
        (tmp_path / "src" / "utils.ts").write_text("code")
        (tmp_path / "package.json").write_text('{"name": "x"}')
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "pkg.js").write_text("dep")

        tech_stack = TechStack(languages=["typescript"])
        classification = classify_files(tmp_path, tech_stack)

        assert any("src" in p and ".ts" in p for p in classification.mutable_patterns)
        # package.json should be protected
        assert any("package.json" in p for p in classification.protected_patterns)

    def test_fallback_classification(self, tmp_path):
        """Classify files when no conventional source dirs exist."""
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "server.py").write_text("code")
        (tmp_path / "app" / "routes.py").write_text("code")

        tech_stack = TechStack(languages=["python"])
        classification = classify_files(tmp_path, tech_stack)

        # Should discover "app" as a source directory
        assert any("app" in p for p in classification.mutable_patterns)


# ---------------------------------------------------------------------------
# Evaluator discovery tests (new for v2)
# ---------------------------------------------------------------------------

class TestDiscoverEvaluators:
    def test_python_project_evaluators(self, tmp_path):
        """Python projects should get complexity, type coverage, and lint evaluators."""
        tech_stack = TechStack(
            languages=["python"],
            test_framework="pytest",
            test_command="uv run pytest",
        )
        evaluators = discover_evaluators(tmp_path, tech_stack)

        names = [e["name"] for e in evaluators]
        assert "test_suite" in names
        assert "code_complexity" in names
        assert "type_coverage" in names
        assert "lint_score" in names

        # Test suite should have highest weight
        test_suite = next(e for e in evaluators if e["name"] == "test_suite")
        assert test_suite["weight"] == 3.0

    def test_rust_project_evaluators(self, tmp_path):
        """Rust projects should get clippy evaluator."""
        tech_stack = TechStack(
            languages=["rust"],
            test_framework="cargo test",
            test_command="cargo test",
        )
        evaluators = discover_evaluators(tmp_path, tech_stack)

        names = [e["name"] for e in evaluators]
        assert "test_suite" in names
        assert "clippy_score" in names

    def test_no_tests_no_test_suite(self, tmp_path):
        """If no test command, don't include test_suite evaluator."""
        tech_stack = TechStack(languages=["python"], test_command="")
        evaluators = discover_evaluators(tmp_path, tech_stack)

        names = [e["name"] for e in evaluators]
        assert "test_suite" not in names

    def test_evaluator_template_keys(self, tmp_path):
        """Each evaluator should have a valid template_key."""
        from autoimprove.prompts import EVALUATOR_TEMPLATES

        tech_stack = TechStack(
            languages=["python"],
            test_framework="pytest",
            test_command="pytest",
        )
        evaluators = discover_evaluators(tmp_path, tech_stack)

        for e in evaluators:
            assert e["template_key"] in EVALUATOR_TEMPLATES, (
                f"Evaluator '{e['name']}' has unknown template_key '{e['template_key']}'"
            )
