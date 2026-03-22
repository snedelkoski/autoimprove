"""LLM prompt templates for autoimprove.

All prompts that are sent to the LLM are centralized here.
This makes them easy to review, iterate on, and test.
"""

# ---------------------------------------------------------------------------
# Repo analysis prompts
# ---------------------------------------------------------------------------

ANALYZE_REPO_SYSTEM = """\
You are an expert software architect analyzing a repository to enable autonomous \
self-improvement. You will be given the repository's file tree and key file contents.

Your job is to produce a precise JSON analysis with the following structure:

{
  "tech_stack": {
    "languages": ["python", "typescript", ...],
    "frameworks": ["fastapi", "react", ...],
    "build_system": "make | npm | cargo | gradle | ...",
    "package_manager": "uv | pip | npm | yarn | pnpm | cargo | go mod | ...",
    "test_framework": "pytest | jest | go test | cargo test | ...",
    "test_command": "the exact shell command to run tests",
    "build_command": "the exact shell command to build (empty if not needed)",
    "run_command": "the exact shell command to run/start the project"
  },
  "file_classification": {
    "mutable_patterns": [
      "src/**/*.py",
      ...
    ],
    "protected_patterns": [
      "tests/**",
      ".github/**",
      "pyproject.toml",
      "Dockerfile",
      ...
    ]
  },
  "repo_summary": "One paragraph describing what this repo does, its purpose, and architecture.",
  "improvement_areas": [
    "Brief description of area where autonomous improvement could help",
    ...
  ]
}

Rules for file classification:
- MUTABLE: Source code files that contain the core logic/functionality. These are what \
the agent will experiment with to improve the software.
- PROTECTED: Tests, CI/CD configs, build configs, package manifests, documentation, \
deployment configs, lock files, generated files. The agent must NOT modify these.
- When in doubt, mark as PROTECTED. It's safer.
- Always protect: tests/, .github/, .gitlab-ci*, Dockerfile*, docker-compose*, \
*.lock, *.toml (package config), *.json (package config), Makefile, README*, LICENSE*, \
.gitignore, .env*

Rules for tech stack detection:
- Be specific with commands. For Python projects with uv, use "uv run pytest" not just "pytest".
- For Node projects, check if it uses npm/yarn/pnpm based on lock files present.
- If no test framework is detected, set test_command to empty string.
- If the repo has a Makefile, check if there's a `make test` target.

Return ONLY valid JSON, no commentary."""

ANALYZE_REPO_USER = """\
## Repository file tree:

{file_tree}

## Key file contents:

{file_contents}
"""

# ---------------------------------------------------------------------------
# Evaluator discovery prompts
# ---------------------------------------------------------------------------

DISCOVER_EVALUATORS_SYSTEM = """\
You are an expert software quality engineer. Given a repository analysis, you will \
design custom evaluation scripts that measure quality metrics BEYOND just running \
the existing test suite.

The goal: create evaluator scripts that an autonomous agent can use to objectively \
measure whether a code change improved the software. Each evaluator must produce a \
numeric score (0.0 to 1.0 where 1.0 is best).

You must return a JSON array of evaluator definitions:

[
  {
    "name": "unique_snake_case_name",
    "description": "What this evaluator measures",
    "weight": 1.0,
    "timeout": 120,
    "script_content": "#!/usr/bin/env python3\\n# /// script\\n# dependencies = [...]\\n# ///\\n\\nimport ...\\n..."
  },
  ...
]

IMPORTANT rules for evaluator scripts:
1. Each script MUST use PEP 723 inline script metadata (the # /// script block) to \
declare its own dependencies. This allows running via `uv run evaluators/name.py`.
2. Each script MUST print a single JSON line to stdout: {"name": "...", "score": 0.85, "details": {...}}
3. Score MUST be a float from 0.0 to 1.0 (higher is better).
4. Scripts run in the ROOT of the target repository (cwd = repo root).
5. Scripts must be self-contained and not import from other evaluator scripts.
6. Scripts should handle errors gracefully — if something fails, output score 0.0 with error details.
7. Scripts should have a reasonable timeout (default 120s).
8. DO NOT duplicate what the test suite already covers. Focus on metrics the developers \
might not have thought of.

Good evaluator ideas (pick what's relevant for this specific repo):
- Code complexity (cyclomatic complexity, cognitive complexity)
- Type annotation coverage (for Python/TypeScript)
- Import graph depth / circular dependency detection
- Dead code detection
- Documentation coverage (docstrings, JSDoc, etc.)
- Error handling coverage (try/except ratio, error boundary coverage)
- API response time / throughput benchmarks (if applicable)
- Bundle size / binary size (if applicable)
- Memory usage profiling (if applicable)
- Code duplication detection
- Security lint (basic static analysis)
- Dependency freshness

Choose 3-6 evaluators most relevant to this specific repository. Quality over quantity."""

DISCOVER_EVALUATORS_USER = """\
## Repository analysis:

{repo_analysis}

## Tech stack:

Languages: {languages}
Frameworks: {frameworks}
Test framework: {test_framework}
Test command: {test_command}

## Repository summary:

{repo_summary}
"""

# ---------------------------------------------------------------------------
# Program.md generation prompts
# ---------------------------------------------------------------------------

GENERATE_PROGRAM_SYSTEM = """\
You are generating a program.md file — this is the instruction manual for an AI agent \
that will autonomously improve a software repository. Think of it as the "research program" \
that guides the agent's experiments.

The program.md follows the pattern from karpathy's autoresearch project:
- It defines the setup procedure
- It defines what the agent CAN and CANNOT do
- It defines the experiment loop (modify → run → evaluate → keep/discard)
- It sets the evaluation criteria
- It gives strategic guidance for what kinds of improvements to try

Tailor the program.md specifically to this repository's tech stack, structure, and purpose.
The agent will read this file at the start of each experiment to understand its mission.

Output ONLY the raw Markdown content for program.md. No code fences around the whole thing."""

GENERATE_PROGRAM_USER = """\
## Repository: {repo_path}

## Summary:
{repo_summary}

## Tech stack:
- Languages: {languages}
- Frameworks: {frameworks}
- Build system: {build_system}
- Package manager: {package_manager}
- Test framework: {test_framework}
- Test command: {test_command}
- Build command: {build_command}

## Mutable files (agent CAN modify):
{mutable_patterns}

## Protected files (agent CANNOT modify):
{protected_patterns}

## Evaluators:
{evaluator_descriptions}

## Improvement areas identified:
{improvement_areas}
"""

# ---------------------------------------------------------------------------
# Experiment proposal prompts
# ---------------------------------------------------------------------------

PROPOSE_EXPERIMENT_SYSTEM = """\
You are an autonomous software improvement agent. Your job is to propose a single, \
concrete experiment to improve the codebase. You will be given:
- The program.md (your mission and constraints)
- The current state of the mutable files
- The history of previous experiments (what worked, what didn't)
- The current evaluation scores

You must return a JSON object:

{
  "title": "Short title for this experiment (< 80 chars)",
  "hypothesis": "Why you think this change will improve the scores",
  "changes": [
    {
      "file": "relative/path/to/file.py",
      "action": "modify",
      "description": "What to change in this file",
      "new_content": "The complete new content of the file"
    }
  ],
  "risk_level": "low | medium | high",
  "expected_improvement": "Which evaluator scores you expect to improve and by how much"
}

Rules:
1. Only modify files matching the mutable patterns.
2. NEVER modify protected files.
3. Make ONE focused change per experiment. Don't try to change everything at once.
4. Look at the experiment history — don't repeat failed experiments.
5. If recent experiments have been discarded, try a different approach entirely.
6. Consider both code quality improvements AND functional improvements.
7. The "new_content" field must contain the COMPLETE file content (not a diff).
8. Be conservative — small improvements that don't break things are better than \
ambitious changes that crash.
9. Reason about WHY a change would improve scores before proposing it.

Return ONLY valid JSON, no commentary."""

PROPOSE_EXPERIMENT_USER = """\
## Program (your mission):

{program_md}

## Current mutable files:

{mutable_files_content}

## Experiment history (recent):

{experiment_history}

## Current evaluation scores:

{current_scores}
"""

# ---------------------------------------------------------------------------
# Eval harness template (generated as a Python file in .autoimprove/)
# ---------------------------------------------------------------------------

EVAL_HARNESS_TEMPLATE = '''\
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pyyaml>=6.0",
# ]
# ///
"""
autoimprove evaluation harness.

This is the fixed evaluation entry point — analogous to prepare.py in autoresearch.
It runs all evaluators and produces a composite score.

DO NOT MODIFY THIS FILE. It is managed by autoimprove.

Usage:
    uv run .autoimprove/eval_harness.py
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import yaml


def run_evaluator(script_path: Path, repo_root: Path, timeout: int) -> dict:
    """Run a single evaluator script and return its result."""
    try:
        result = subprocess.run(
            ["uv", "run", str(script_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(repo_root),
        )
        if result.returncode != 0:
            return {{
                "name": script_path.stem,
                "score": 0.0,
                "details": {{
                    "error": f"Evaluator exited with code {{result.returncode}}",
                    "stderr": result.stderr[-500:] if result.stderr else "",
                }},
            }}
        # Parse last JSON line from stdout
        for line in reversed(result.stdout.strip().splitlines()):
            line = line.strip()
            if line.startswith("{{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        return {{
            "name": script_path.stem,
            "score": 0.0,
            "details": {{"error": "No valid JSON output from evaluator", "stdout": result.stdout[-500:]}},
        }}
    except subprocess.TimeoutExpired:
        return {{
            "name": script_path.stem,
            "score": 0.0,
            "details": {{"error": f"Evaluator timed out after {{timeout}}s"}},
        }}
    except Exception as e:
        return {{
            "name": script_path.stem,
            "score": 0.0,
            "details": {{"error": str(e)}},
        }}


def run_test_suite(test_command: str, repo_root: Path, timeout: int = 300) -> dict:
    """Run the repo's own test suite and return pass rate as score."""
    if not test_command:
        return {{
            "name": "test_suite",
            "score": 1.0,
            "details": {{"info": "No test command configured, assuming pass"}},
        }}
    try:
        result = subprocess.run(
            test_command.split(),
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(repo_root),
        )
        passed = result.returncode == 0
        return {{
            "name": "test_suite",
            "score": 1.0 if passed else 0.0,
            "details": {{
                "passed": passed,
                "returncode": result.returncode,
                "stdout_tail": result.stdout[-1000:] if result.stdout else "",
                "stderr_tail": result.stderr[-500:] if result.stderr else "",
            }},
        }}
    except subprocess.TimeoutExpired:
        return {{
            "name": "test_suite",
            "score": 0.0,
            "details": {{"error": f"Test suite timed out after {{timeout}}s"}},
        }}
    except Exception as e:
        return {{
            "name": "test_suite",
            "score": 0.0,
            "details": {{"error": str(e)}},
        }}


def main():
    # Determine paths
    harness_path = Path(__file__).resolve()
    autoimprove_dir = harness_path.parent
    repo_root = autoimprove_dir.parent

    # Load config
    config_path = autoimprove_dir / "config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    t_start = time.time()
    results = []
    evaluator_configs = {{e["name"]: e for e in config.get("evaluators", [])}}

    # 1. Run the project's own test suite (weight = 3.0, highest priority)
    test_command = config.get("tech_stack", {{}}).get("test_command", "")
    test_result = run_test_suite(test_command, repo_root)
    test_result["weight"] = 3.0
    results.append(test_result)

    # 2. Run each custom evaluator
    evaluators_dir = autoimprove_dir / "evaluators"
    if evaluators_dir.exists():
        for script_path in sorted(evaluators_dir.glob("*.py")):
            if script_path.name.startswith("_"):
                continue
            econf = evaluator_configs.get(script_path.stem, {{}})
            if not econf.get("enabled", True):
                continue
            timeout = econf.get("timeout", 120)
            result = run_evaluator(script_path, repo_root, timeout)
            result["weight"] = econf.get("weight", 1.0)
            results.append(result)

    # 3. Compute composite score
    total_weight = sum(r["weight"] for r in results)
    if total_weight > 0:
        composite = sum(r["score"] * r["weight"] for r in results) / total_weight
    else:
        composite = 0.0

    elapsed = time.time() - t_start

    # Output
    output = {{
        "composite_score": round(composite, 6),
        "elapsed_seconds": round(elapsed, 1),
        "evaluators": results,
    }}
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
'''

# ---------------------------------------------------------------------------
# Test suite evaluator template
# ---------------------------------------------------------------------------

TEST_SUITE_EVALUATOR_TEMPLATE = '''\
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Test suite pass rate evaluator.
Runs the project's test command and reports pass/fail as a 0.0/1.0 score.
"""

import json
import subprocess
import sys


def main():
    test_command = {test_command!r}
    if not test_command:
        print(json.dumps({{"name": "test_suite", "score": 1.0, "details": {{"info": "No test command"}}}}))
        return

    try:
        result = subprocess.run(
            test_command.split(),
            capture_output=True,
            text=True,
            timeout=300,
        )
        passed = result.returncode == 0
        print(json.dumps({{
            "name": "test_suite",
            "score": 1.0 if passed else 0.0,
            "details": {{
                "passed": passed,
                "returncode": result.returncode,
                "stdout_tail": result.stdout[-500:] if result.stdout else "",
                "stderr_tail": result.stderr[-500:] if result.stderr else "",
            }},
        }}))
    except subprocess.TimeoutExpired:
        print(json.dumps({{"name": "test_suite", "score": 0.0, "details": {{"error": "timeout"}}}}))
    except Exception as e:
        print(json.dumps({{"name": "test_suite", "score": 0.0, "details": {{"error": str(e)}}}}))


if __name__ == "__main__":
    main()
'''
