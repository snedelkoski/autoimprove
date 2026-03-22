"""Tests for autoimprove analyzer module."""

import os
from pathlib import Path

import pytest

from autoimprove.analyzer import (
    SKIP_DIRS,
    format_file_contents,
    format_file_tree,
    read_key_files,
    scan_file_tree,
)


class TestScanFileTree:
    def test_basic_scan(self, tmp_path):
        # Create a simple repo structure
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
