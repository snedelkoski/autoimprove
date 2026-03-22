"""Repository analyzer for autoimprove.

Examines a target repository to detect its tech stack, file structure,
test setup, and classify files into mutable vs protected categories.

All detection is heuristic-based — no LLM calls. The coding agent that
runs autoimprove can refine the generated artifacts with its own intelligence.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from autoimprove.config import FileClassification, TechStack

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# File tree scanning
# ---------------------------------------------------------------------------

# Directories to always skip when scanning
SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
    ".eggs", ".autoimprove", ".next", ".nuxt", "target",
    "vendor", "coverage", ".coverage", "htmlcov", "env",
}

# Binary / large file extensions to skip reading
SKIP_EXTENSIONS = {
    ".pyc", ".pyo", ".so", ".o", ".a", ".dylib", ".dll", ".exe",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".webp",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".rar", ".7z",
    ".whl", ".egg", ".db", ".sqlite", ".sqlite3",
    ".woff", ".woff2", ".ttf", ".eot",
    ".lock",
    ".min.js", ".min.css",
}

# Key files to always try to read (if they exist)
KEY_FILES = [
    "README.md", "README.rst", "README.txt", "README",
    "pyproject.toml", "setup.py", "setup.cfg",
    "package.json", "tsconfig.json",
    "Cargo.toml",
    "go.mod",
    "Makefile", "Justfile",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "Gemfile", "build.gradle", "build.gradle.kts", "pom.xml",
    "requirements.txt", "Pipfile",
    "deno.json", "deno.jsonc",
]

# Max chars to read from any single file
MAX_FILE_CHARS = 8000
# Max total chars for context
MAX_TOTAL_CHARS = 80000
# Max files to include in the tree
MAX_TREE_FILES = 500

# Source code extensions by language
LANGUAGE_EXTENSIONS: dict[str, list[str]] = {
    "python": [".py"],
    "javascript": [".js", ".mjs", ".cjs"],
    "typescript": [".ts", ".mts", ".cts"],
    "jsx": [".jsx"],
    "tsx": [".tsx"],
    "rust": [".rs"],
    "go": [".go"],
    "java": [".java"],
    "kotlin": [".kt", ".kts"],
    "ruby": [".rb"],
    "c": [".c", ".h"],
    "cpp": [".cpp", ".cc", ".cxx", ".hpp", ".hh"],
    "csharp": [".cs"],
    "swift": [".swift"],
    "php": [".php"],
    "scala": [".scala"],
    "elixir": [".ex", ".exs"],
    "haskell": [".hs"],
    "lua": [".lua"],
    "zig": [".zig"],
}

# Reverse mapping: extension -> language
_EXT_TO_LANG: dict[str, str] = {}
for _lang, _exts in LANGUAGE_EXTENSIONS.items():
    for _ext in _exts:
        _EXT_TO_LANG[_ext] = _lang


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
        fpath = repo_path / pattern
        if fpath.exists() and pattern not in contents and total_chars < MAX_TOTAL_CHARS:
            try:
                text = fpath.read_text(errors="replace")[:MAX_FILE_CHARS]
                contents[pattern] = text
                total_chars += len(text)
            except (OSError, UnicodeDecodeError):
                pass

    # Then, read a sample of source files for context
    source_extensions = set(_EXT_TO_LANG.keys())
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
# Heuristic tech stack detection
# ---------------------------------------------------------------------------

def _detect_languages(repo_path: Path, file_tree: list[str]) -> list[str]:
    """Detect programming languages from file extensions."""
    lang_counts: dict[str, int] = {}
    for rel_path in file_tree:
        suffix = Path(rel_path).suffix.lower()
        lang = _EXT_TO_LANG.get(suffix)
        if lang:
            # Merge jsx/tsx into javascript/typescript
            if lang == "jsx":
                lang = "javascript"
            elif lang == "tsx":
                lang = "typescript"
            lang_counts[lang] = lang_counts.get(lang, 0) + 1

    # Sort by count descending, return languages with at least 1 file
    return [lang for lang, _ in sorted(lang_counts.items(), key=lambda x: -x[1])]


def _detect_frameworks(repo_path: Path, file_tree: list[str]) -> list[str]:
    """Detect frameworks from config files and dependencies."""
    frameworks: list[str] = []

    # Python frameworks
    pyproject = repo_path / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text()
            for fw, markers in {
                "fastapi": ["fastapi"],
                "django": ["django"],
                "flask": ["flask"],
                "starlette": ["starlette"],
                "pytorch": ["torch"],
                "tensorflow": ["tensorflow"],
                "jax": ["jax"],
                "sqlalchemy": ["sqlalchemy"],
                "pydantic": ["pydantic"],
                "click": ["click"],
                "typer": ["typer"],
            }.items():
                for marker in markers:
                    if marker in content.lower():
                        frameworks.append(fw)
                        break
        except OSError:
            pass

    # Check requirements.txt / setup.py too
    for req_file in ["requirements.txt", "setup.py", "setup.cfg", "Pipfile"]:
        fpath = repo_path / req_file
        if fpath.exists():
            try:
                content = fpath.read_text().lower()
                for fw, markers in {
                    "fastapi": ["fastapi"],
                    "django": ["django"],
                    "flask": ["flask"],
                    "pytorch": ["torch"],
                    "tensorflow": ["tensorflow"],
                }.items():
                    if fw not in frameworks:
                        for marker in markers:
                            if marker in content:
                                frameworks.append(fw)
                                break
            except OSError:
                pass

    # JavaScript/TypeScript frameworks
    pkg_json = repo_path / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            all_deps = {}
            all_deps.update(pkg.get("dependencies", {}))
            all_deps.update(pkg.get("devDependencies", {}))
            for fw, pkg_names in {
                "react": ["react"],
                "next.js": ["next"],
                "vue": ["vue"],
                "nuxt": ["nuxt"],
                "angular": ["@angular/core"],
                "svelte": ["svelte"],
                "express": ["express"],
                "fastify": ["fastify"],
                "nestjs": ["@nestjs/core"],
                "hono": ["hono"],
                "vite": ["vite"],
                "webpack": ["webpack"],
                "tailwindcss": ["tailwindcss"],
            }.items():
                for pkg_name in pkg_names:
                    if pkg_name in all_deps:
                        frameworks.append(fw)
                        break
        except (OSError, json.JSONDecodeError):
            pass

    # Rust frameworks
    cargo_toml = repo_path / "Cargo.toml"
    if cargo_toml.exists():
        try:
            content = cargo_toml.read_text().lower()
            for fw, markers in {
                "actix-web": ["actix-web"],
                "axum": ["axum"],
                "tokio": ["tokio"],
                "rocket": ["rocket"],
                "warp": ["warp"],
            }.items():
                for marker in markers:
                    if marker in content:
                        frameworks.append(fw)
                        break
        except OSError:
            pass

    # Go frameworks
    go_mod = repo_path / "go.mod"
    if go_mod.exists():
        try:
            content = go_mod.read_text().lower()
            for fw, markers in {
                "gin": ["github.com/gin-gonic/gin"],
                "echo": ["github.com/labstack/echo"],
                "fiber": ["github.com/gofiber/fiber"],
                "chi": ["github.com/go-chi/chi"],
            }.items():
                for marker in markers:
                    if marker in content:
                        frameworks.append(fw)
                        break
        except OSError:
            pass

    return frameworks


def _detect_package_manager(repo_path: Path) -> str:
    """Detect the package manager from lock files and config."""
    # Python
    if (repo_path / "uv.lock").exists():
        return "uv"
    if (repo_path / "poetry.lock").exists():
        return "poetry"
    if (repo_path / "Pipfile.lock").exists():
        return "pipenv"
    if (repo_path / "requirements.txt").exists():
        return "pip"

    # JavaScript/TypeScript
    if (repo_path / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (repo_path / "yarn.lock").exists():
        return "yarn"
    if (repo_path / "bun.lockb").exists() or (repo_path / "bun.lock").exists():
        return "bun"
    if (repo_path / "package-lock.json").exists():
        return "npm"
    if (repo_path / "deno.lock").exists():
        return "deno"

    # Rust
    if (repo_path / "Cargo.lock").exists() or (repo_path / "Cargo.toml").exists():
        return "cargo"

    # Go
    if (repo_path / "go.sum").exists() or (repo_path / "go.mod").exists():
        return "go"

    # Ruby
    if (repo_path / "Gemfile.lock").exists():
        return "bundler"

    # Java/Kotlin
    if (repo_path / "build.gradle").exists() or (repo_path / "build.gradle.kts").exists():
        return "gradle"
    if (repo_path / "pom.xml").exists():
        return "maven"

    # Fallback: check if pyproject.toml exists (could be any Python tool)
    if (repo_path / "pyproject.toml").exists():
        return "pip"

    return ""


def _detect_build_system(repo_path: Path) -> str:
    """Detect the build system."""
    if (repo_path / "Makefile").exists():
        return "make"
    if (repo_path / "Justfile").exists():
        return "just"
    if (repo_path / "build.gradle").exists() or (repo_path / "build.gradle.kts").exists():
        return "gradle"
    if (repo_path / "pom.xml").exists():
        return "maven"
    if (repo_path / "CMakeLists.txt").exists():
        return "cmake"
    if (repo_path / "Cargo.toml").exists():
        return "cargo"

    # JS build tools
    pkg_json = repo_path / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            scripts = pkg.get("scripts", {})
            if "build" in scripts:
                return "npm"
        except (OSError, json.JSONDecodeError):
            pass

    return ""


def _detect_test_framework(
    repo_path: Path,
    languages: list[str],
    package_manager: str,
) -> tuple[str, str]:
    """Detect test framework and test command.

    Returns (test_framework, test_command).
    """
    # Python
    if "python" in languages:
        pyproject = repo_path / "pyproject.toml"
        has_pytest_config = False
        if pyproject.exists():
            try:
                content = pyproject.read_text()
                if "[tool.pytest" in content or "pytest" in content.lower():
                    has_pytest_config = True
            except OSError:
                pass

        # Check for setup.cfg pytest config
        setup_cfg = repo_path / "setup.cfg"
        if setup_cfg.exists():
            try:
                content = setup_cfg.read_text()
                if "[tool:pytest]" in content:
                    has_pytest_config = True
            except OSError:
                pass

        # Check for pytest.ini
        if (repo_path / "pytest.ini").exists():
            has_pytest_config = True

        # Check for test directories
        has_tests_dir = (
            (repo_path / "tests").is_dir()
            or (repo_path / "test").is_dir()
        )

        if has_pytest_config or has_tests_dir:
            if package_manager == "uv":
                return "pytest", "uv run pytest"
            elif package_manager == "poetry":
                return "pytest", "poetry run pytest"
            else:
                return "pytest", "pytest"

        # Check for unittest
        if has_tests_dir:
            return "unittest", "python -m unittest discover"

    # JavaScript/TypeScript
    if "javascript" in languages or "typescript" in languages:
        pkg_json = repo_path / "package.json"
        if pkg_json.exists():
            try:
                pkg = json.loads(pkg_json.read_text())
                all_deps = {}
                all_deps.update(pkg.get("dependencies", {}))
                all_deps.update(pkg.get("devDependencies", {}))
                scripts = pkg.get("scripts", {})

                # Detect test framework from deps
                if "vitest" in all_deps:
                    run_prefix = {"pnpm": "pnpm", "yarn": "yarn", "bun": "bun"}.get(
                        package_manager, "npx"
                    )
                    return "vitest", f"{run_prefix} vitest run"
                elif "jest" in all_deps:
                    run_prefix = {"pnpm": "pnpm", "yarn": "yarn", "bun": "bun"}.get(
                        package_manager, "npx"
                    )
                    return "jest", f"{run_prefix} jest"
                elif "mocha" in all_deps:
                    run_prefix = {"pnpm": "pnpm", "yarn": "yarn", "bun": "bun"}.get(
                        package_manager, "npx"
                    )
                    return "mocha", f"{run_prefix} mocha"

                # Fallback: check scripts.test
                if "test" in scripts:
                    test_script = scripts["test"]
                    run_cmd = {"pnpm": "pnpm test", "yarn": "yarn test", "bun": "bun test"}.get(
                        package_manager, "npm test"
                    )
                    # Try to detect framework from test script
                    if "vitest" in test_script:
                        return "vitest", run_cmd
                    elif "jest" in test_script:
                        return "jest", run_cmd
                    elif "mocha" in test_script:
                        return "mocha", run_cmd
                    else:
                        return "", run_cmd
            except (OSError, json.JSONDecodeError):
                pass

    # Rust
    if "rust" in languages:
        return "cargo test", "cargo test"

    # Go
    if "go" in languages:
        return "go test", "go test ./..."

    # Ruby
    if "ruby" in languages:
        if (repo_path / "Gemfile").exists():
            try:
                content = (repo_path / "Gemfile").read_text().lower()
                if "rspec" in content:
                    return "rspec", "bundle exec rspec"
                elif "minitest" in content:
                    return "minitest", "bundle exec rake test"
            except OSError:
                pass

    # Java/Kotlin
    if "java" in languages or "kotlin" in languages:
        if (repo_path / "build.gradle").exists() or (repo_path / "build.gradle.kts").exists():
            return "junit", "gradle test"
        if (repo_path / "pom.xml").exists():
            return "junit", "mvn test"

    # Check for Makefile test target
    makefile = repo_path / "Makefile"
    if makefile.exists():
        try:
            content = makefile.read_text()
            # Look for test target (line starting with "test:")
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("test:") or stripped.startswith("test "):
                    return "", "make test"
        except OSError:
            pass

    return "", ""


def _detect_build_command(
    repo_path: Path,
    languages: list[str],
    package_manager: str,
    build_system: str,
) -> str:
    """Detect the build command."""
    if build_system == "make":
        try:
            content = (repo_path / "Makefile").read_text()
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("build:") or stripped.startswith("build "):
                    return "make build"
        except OSError:
            pass

    if build_system == "cargo":
        return "cargo build"

    if build_system == "gradle":
        return "gradle build"

    if build_system == "maven":
        return "mvn package"

    # JS/TS build
    pkg_json = repo_path / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            if "build" in pkg.get("scripts", {}):
                prefix = {"pnpm": "pnpm", "yarn": "yarn", "bun": "bun"}.get(
                    package_manager, "npm run"
                )
                return f"{prefix} build"
        except (OSError, json.JSONDecodeError):
            pass

    return ""


def _detect_run_command(
    repo_path: Path,
    languages: list[str],
    package_manager: str,
    frameworks: list[str],
) -> str:
    """Detect the run/start command."""
    # JS/TS
    pkg_json = repo_path / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            scripts = pkg.get("scripts", {})
            prefix = {"pnpm": "pnpm", "yarn": "yarn", "bun": "bun"}.get(
                package_manager, "npm run"
            )
            if "dev" in scripts:
                return f"{prefix} dev"
            elif "start" in scripts:
                start_prefix = {"pnpm": "pnpm", "yarn": "yarn", "bun": "bun"}.get(
                    package_manager, "npm"
                )
                return f"{start_prefix} start"
        except (OSError, json.JSONDecodeError):
            pass

    # Python
    if "python" in languages:
        if "fastapi" in frameworks:
            if package_manager == "uv":
                return "uv run uvicorn main:app"
            return "uvicorn main:app"
        if "flask" in frameworks:
            if package_manager == "uv":
                return "uv run flask run"
            return "flask run"
        if "django" in frameworks:
            if package_manager == "uv":
                return "uv run python manage.py runserver"
            return "python manage.py runserver"

    # Rust
    if "rust" in languages:
        return "cargo run"

    # Go
    if "go" in languages:
        return "go run ."

    return ""


def _generate_repo_summary(
    repo_path: Path,
    languages: list[str],
    frameworks: list[str],
) -> str:
    """Generate a one-line repo summary from README and project files."""
    # Try to extract description from pyproject.toml
    pyproject = repo_path / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text()
            for line in content.splitlines():
                if line.strip().startswith("description"):
                    # Parse: description = "..."
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        desc = parts[1].strip().strip('"').strip("'")
                        if desc and desc != "":
                            return desc
        except OSError:
            pass

    # Try package.json description
    pkg_json = repo_path / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            desc = pkg.get("description", "")
            if desc:
                return desc
        except (OSError, json.JSONDecodeError):
            pass

    # Try Cargo.toml description
    cargo_toml = repo_path / "Cargo.toml"
    if cargo_toml.exists():
        try:
            content = cargo_toml.read_text()
            for line in content.splitlines():
                if line.strip().startswith("description"):
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        desc = parts[1].strip().strip('"').strip("'")
                        if desc:
                            return desc
        except OSError:
            pass

    # Fallback
    lang_str = ", ".join(languages[:3]) if languages else "unknown"
    fw_str = f" with {', '.join(frameworks[:3])}" if frameworks else ""
    repo_name = repo_path.name
    return f"{repo_name} — a {lang_str}{fw_str} project"


def detect_tech_stack(repo_path: Path) -> tuple[TechStack, str]:
    """Detect the technology stack of a repository.

    Returns (TechStack, repo_summary).
    """
    file_tree = scan_file_tree(repo_path)

    languages = _detect_languages(repo_path, file_tree)
    frameworks = _detect_frameworks(repo_path, file_tree)
    package_manager = _detect_package_manager(repo_path)
    build_system = _detect_build_system(repo_path)
    test_framework, test_command = _detect_test_framework(
        repo_path, languages, package_manager
    )
    build_command = _detect_build_command(
        repo_path, languages, package_manager, build_system
    )
    run_command = _detect_run_command(
        repo_path, languages, package_manager, frameworks
    )
    repo_summary = _generate_repo_summary(repo_path, languages, frameworks)

    tech_stack = TechStack(
        languages=languages,
        frameworks=frameworks,
        build_system=build_system,
        package_manager=package_manager,
        test_framework=test_framework,
        test_command=test_command,
        build_command=build_command,
        run_command=run_command,
    )

    return tech_stack, repo_summary


# ---------------------------------------------------------------------------
# Heuristic file classification
# ---------------------------------------------------------------------------

# Always-protected patterns
PROTECTED_PATTERNS = [
    "tests/**",
    "test/**",
    "__tests__/**",
    "**/*.test.*",
    "**/*.spec.*",
    "**/*_test.*",
    "**/*_spec.*",
    ".github/**",
    ".gitlab-ci*",
    ".circleci/**",
    "Dockerfile*",
    "docker-compose*",
    "*.lock",
    ".gitignore",
    ".gitattributes",
    ".env*",
    "LICENSE*",
    "LICENCE*",
    "README*",
    "CHANGELOG*",
    "CONTRIBUTING*",
    "CODE_OF_CONDUCT*",
    ".autoimprove/**",
    "*.toml",
    "*.cfg",
    "*.ini",
    "Makefile",
    "Justfile",
    "Gemfile",
    "Rakefile",
    "*.lock",
    "*.sum",
    "go.mod",
]

# Source directory conventions per ecosystem
SOURCE_DIR_PATTERNS: dict[str, list[str]] = {
    "python": ["src/**/*.py", "lib/**/*.py", "app/**/*.py"],
    "javascript": ["src/**/*.js", "src/**/*.mjs", "lib/**/*.js", "app/**/*.js"],
    "typescript": ["src/**/*.ts", "src/**/*.mts", "lib/**/*.ts", "app/**/*.ts"],
    "rust": ["src/**/*.rs"],
    "go": ["cmd/**/*.go", "internal/**/*.go", "pkg/**/*.go"],
    "java": ["src/main/**/*.java"],
    "kotlin": ["src/main/**/*.kt"],
    "ruby": ["lib/**/*.rb", "app/**/*.rb"],
    "csharp": ["src/**/*.cs"],
    "swift": ["Sources/**/*.swift"],
    "php": ["src/**/*.php", "app/**/*.php"],
}

# Fallback: any source file with these extensions is mutable
FALLBACK_MUTABLE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".mjs", ".mts",
    ".rs", ".go", ".java", ".kt", ".rb", ".cs", ".swift",
    ".php", ".scala", ".ex", ".exs", ".hs", ".lua", ".zig",
    ".c", ".cpp", ".cc", ".h", ".hpp",
}


def classify_files(
    repo_path: Path,
    tech_stack: TechStack,
) -> FileClassification:
    """Classify repository files into mutable and protected patterns.

    Protected = tests, CI, configs, docs, lock files, etc.
    Mutable = source code the agent can experiment on.
    """
    file_tree = scan_file_tree(repo_path)

    # Start with always-protected patterns
    protected = list(PROTECTED_PATTERNS)

    # Add package-manager-specific configs to protected
    pkg_configs = [
        "package.json", "package-lock.json",
        "tsconfig.json", "tsconfig*.json",
        "pyproject.toml", "setup.py", "setup.cfg",
        "Cargo.toml", "Cargo.lock",
        "go.mod", "go.sum",
        "pom.xml", "build.gradle", "build.gradle.kts",
        "Pipfile", "Pipfile.lock",
        "requirements.txt", "requirements*.txt",
        "deno.json", "deno.jsonc", "deno.lock",
    ]
    for cfg in pkg_configs:
        if cfg not in protected:
            protected.append(cfg)

    # Determine mutable patterns
    mutable: list[str] = []

    # Check for known source directory conventions
    for lang in tech_stack.languages:
        patterns = SOURCE_DIR_PATTERNS.get(lang, [])
        for pattern in patterns:
            # Check if the base directory actually exists
            base_dir = pattern.split("/")[0]
            if (repo_path / base_dir).is_dir():
                mutable.append(pattern)

    # If no conventional source dirs found, scan for source files
    if not mutable:
        # Find directories containing source files
        source_dirs: set[str] = set()
        for rel_path in file_tree:
            suffix = Path(rel_path).suffix.lower()
            if suffix in FALLBACK_MUTABLE_EXTENSIONS:
                # Get the top-level directory
                parts = Path(rel_path).parts
                if len(parts) > 1:
                    top_dir = parts[0]
                    # Skip known non-source dirs
                    if top_dir not in {
                        "tests", "test", "__tests__", "docs", "doc",
                        ".github", ".gitlab", ".circleci",
                        "scripts", "bin", "config", "configs",
                    }:
                        source_dirs.add(top_dir)
                else:
                    # Root-level source file
                    ext_glob = f"*{suffix}"
                    if ext_glob not in mutable:
                        mutable.append(ext_glob)

        # Add discovered source directories
        for src_dir in sorted(source_dirs):
            # Find what extensions exist in this directory
            for rel_path in file_tree:
                if rel_path.startswith(src_dir + os.sep):
                    suffix = Path(rel_path).suffix.lower()
                    if suffix in FALLBACK_MUTABLE_EXTENSIONS:
                        pattern = f"{src_dir}/**/*{suffix}"
                        if pattern not in mutable:
                            mutable.append(pattern)

    # Deduplicate
    mutable = list(dict.fromkeys(mutable))
    protected = list(dict.fromkeys(protected))

    return FileClassification(
        mutable_patterns=mutable,
        protected_patterns=protected,
    )


# ---------------------------------------------------------------------------
# Evaluator discovery — template-based
# ---------------------------------------------------------------------------

def discover_evaluators(
    repo_path: Path,
    tech_stack: TechStack,
) -> list[dict[str, Any]]:
    """Discover which evaluator templates are relevant for this repo.

    Returns a list of evaluator definitions with:
    - name: str
    - description: str
    - weight: float
    - timeout: int
    - template_key: str (key into EVALUATOR_TEMPLATES in prompts.py)
    """
    evaluators: list[dict[str, Any]] = []

    # Always include test suite if a test command is detected
    if tech_stack.test_command:
        evaluators.append({
            "name": "test_suite",
            "description": "Runs the project's test suite and reports pass/fail",
            "weight": 3.0,
            "timeout": 300,
            "template_key": "test_suite",
            "template_vars": {"test_command": tech_stack.test_command},
        })

    # Python-specific evaluators
    if "python" in tech_stack.languages:
        evaluators.append({
            "name": "code_complexity",
            "description": "Measures average cyclomatic complexity of Python source files",
            "weight": 1.0,
            "timeout": 120,
            "template_key": "code_complexity_python",
            "template_vars": {},
        })
        evaluators.append({
            "name": "type_coverage",
            "description": "Measures type annotation coverage using mypy",
            "weight": 1.0,
            "timeout": 120,
            "template_key": "type_coverage_python",
            "template_vars": {},
        })
        evaluators.append({
            "name": "lint_score",
            "description": "Measures code quality using ruff linter",
            "weight": 1.5,
            "timeout": 120,
            "template_key": "lint_python",
            "template_vars": {},
        })

    # JavaScript/TypeScript evaluators
    if "javascript" in tech_stack.languages or "typescript" in tech_stack.languages:
        evaluators.append({
            "name": "lint_score",
            "description": "Measures code quality using eslint",
            "weight": 1.5,
            "timeout": 120,
            "template_key": "lint_js",
            "template_vars": {},
        })

    # Rust evaluators
    if "rust" in tech_stack.languages:
        evaluators.append({
            "name": "clippy_score",
            "description": "Measures code quality using cargo clippy warnings",
            "weight": 1.5,
            "timeout": 120,
            "template_key": "clippy_rust",
            "template_vars": {},
        })

    # Go evaluators
    if "go" in tech_stack.languages:
        evaluators.append({
            "name": "vet_score",
            "description": "Measures code quality using go vet",
            "weight": 1.5,
            "timeout": 120,
            "template_key": "vet_go",
            "template_vars": {},
        })

    return evaluators
