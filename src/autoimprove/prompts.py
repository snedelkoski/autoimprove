"""Templates for autoimprove.

Contains the program.md template (agent instructions), the evaluation
harness script, and evaluator script templates for common tech stacks.

No LLM prompts — this tool is designed to be run BY a coding agent
(Claude Code, OpenCode, Copilot, etc.) which IS the LLM.
"""

# ---------------------------------------------------------------------------
# program.md template — the agent instruction document
# ---------------------------------------------------------------------------

PROGRAM_MD_TEMPLATE = """\
# autoimprove

Autonomous self-improvement program for **{repo_name}**.

> {repo_summary}

## Setup

To set up a new improvement session:

1. **Read this file** for full context on the repo and the experiment loop.
2. **Agree on a run tag**: propose a tag based on today's date (e.g. `mar5`). \
The branch `autoimprove/<tag>` must not already exist.
3. **Create the branch**: `git checkout -b autoimprove/<tag>` from current main/master.
4. **Read the in-scope files**: Familiarize yourself with the codebase structure:
   - This `program.md` — your mission and constraints.
   - `.autoimprove/config.yaml` — detected tech stack, file classification, evaluators.
   - `.autoimprove/eval_harness.py` — the fixed evaluation script. **Do not modify.**
   - `.autoimprove/evaluators/` — individual evaluator scripts. **Do not modify.**
5. **Verify baseline**: Check that `.autoimprove/baselines/baseline.json` exists. \
If not, run `uv run .autoimprove/eval_harness.py` to establish baseline.
6. **Initialize results.tsv** if it only has the header row. The baseline will be \
recorded after the first run.
7. **Confirm and go**: Confirm setup looks good, then start experimenting.

## Tech Stack

- **Languages**: {languages}
- **Frameworks**: {frameworks}
- **Package manager**: {package_manager}
- **Build system**: {build_system}
- **Test framework**: {test_framework}
- **Test command**: `{test_command}`
- **Build command**: `{build_command}`
- **Run command**: `{run_command}`

## What You CAN Do

- Modify files matching these patterns (the "mutable surface area"):
{mutable_patterns_list}
- Refactor, optimize, simplify, improve error handling, add type annotations, \
improve performance, reduce complexity — anything that improves the evaluation scores.

## What You CANNOT Do

- Modify protected files (tests, CI, configs, docs, lock files, evaluation scripts):
{protected_patterns_list}
- Install new dependencies or modify package manifests.
- Modify anything in `.autoimprove/` — the eval harness and evaluators are fixed.
- Modify tests — they are the ground truth.

## Evaluation

The evaluation harness measures software quality across multiple dimensions. Run it:

```bash
uv run .autoimprove/eval_harness.py
```

It outputs JSON with a composite score (0.0-1.0, higher is better) and per-evaluator scores:

```json
{{
  "composite_score": 0.85,
  "elapsed_seconds": 12.3,
  "evaluators": [
    {{"name": "test_suite", "score": 1.0, "weight": 3.0, ...}},
    {{"name": "code_complexity", "score": 0.7, "weight": 1.0, ...}},
    ...
  ]
}}
```

### Evaluators

{evaluator_descriptions}

The composite score is a weighted average. **The test suite has the highest weight** \
(3.0) — never break the tests.

## The Experiment Loop

LOOP FOREVER:

1. Look at the current state of the codebase and evaluation scores.
2. Come up with a specific, focused improvement to try.
3. `git commit` the change.
4. Run the evaluation: `uv run .autoimprove/eval_harness.py > .autoimprove/run.log 2>&1`
5. Read the results: check the composite_score from `.autoimprove/run.log`
6. If the eval crashed, read the log to understand why. Try to fix if it's a simple \
bug. If the approach is fundamentally broken, give up on it.
7. Record the results in `.autoimprove/results.tsv`
8. If composite_score **improved** (higher than baseline), KEEP the commit and update \
the baseline.
9. If composite_score is **equal or worse**, DISCARD the commit: \
`git reset --hard HEAD~1`
10. Go to step 1.

## Logging Results

Log every experiment to `.autoimprove/results.tsv` (tab-separated).

The TSV has a header row and 4 columns:

```
experiment\tcomposite_score\tstatus\tdescription
```

1. experiment: short identifier (e.g. `exp_0001`, or git short hash)
2. composite_score: the score achieved (e.g. `0.850000`) — use `0.000000` for crashes
3. status: `keep`, `discard`, or `crash`
4. description: short text describing what this experiment tried

Example:

```
experiment\tcomposite_score\tstatus\tdescription
a1b2c3d\t0.850000\tkeep\tbaseline
b2c3d4e\t0.870000\tkeep\treduced cyclomatic complexity in parser.py
c3d4e5f\t0.830000\tdiscard\taggressively inlined utility functions
d4e5f6g\t0.000000\tcrash\trefactored imports (circular dependency)
```

## Strategy

**The goal: maximize the composite evaluation score.**

The simplicity criterion: all else being equal, simpler is better. A small improvement \
that adds ugly complexity is not worth it. Conversely, removing code and getting equal \
or better results is a great outcome — that's a simplification win. When evaluating \
whether to keep a change, weigh the complexity cost against the improvement magnitude.

Good experiment ideas:
- Reduce cyclomatic complexity in complex functions
- Add missing type annotations
- Improve error handling (replace bare excepts, add specific exception types)
- Remove dead code
- Simplify overly nested logic
- Extract helper functions for readability
- Fix lint warnings
- Improve documentation/docstrings
- Optimize hot paths (if benchmarks exist)

**Crashes**: If a run crashes, use your judgment. If it's a typo or missing import, \
fix it and re-run. If the idea itself is broken, log "crash" and move on.

**NEVER STOP**: Once the experiment loop begins, do NOT pause to ask the human if you \
should continue. The human might be away and expects you to work **indefinitely** until \
manually stopped. If you run out of ideas, think harder — re-read the source code, \
try combining previous near-misses, try more radical approaches. The loop runs until \
the human interrupts you.
"""

# ---------------------------------------------------------------------------
# Eval harness template
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
            return {
                "name": script_path.stem,
                "score": 0.0,
                "details": {
                    "error": f"Evaluator exited with code {result.returncode}",
                    "stderr": result.stderr[-500:] if result.stderr else "",
                },
            }
        # Parse last JSON line from stdout
        for line in reversed(result.stdout.strip().splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        return {
            "name": script_path.stem,
            "score": 0.0,
            "details": {"error": "No valid JSON output from evaluator", "stdout": result.stdout[-500:]},
        }
    except subprocess.TimeoutExpired:
        return {
            "name": script_path.stem,
            "score": 0.0,
            "details": {"error": f"Evaluator timed out after {timeout}s"},
        }
    except Exception as e:
        return {
            "name": script_path.stem,
            "score": 0.0,
            "details": {"error": str(e)},
        }


def run_test_suite(test_command: str, repo_root: Path, timeout: int = 300) -> dict:
    """Run the repo's own test suite and return pass rate as score."""
    if not test_command:
        return {
            "name": "test_suite",
            "score": 1.0,
            "details": {"info": "No test command configured, assuming pass"},
        }
    try:
        result = subprocess.run(
            test_command.split(),
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(repo_root),
        )
        passed = result.returncode == 0
        return {
            "name": "test_suite",
            "score": 1.0 if passed else 0.0,
            "details": {
                "passed": passed,
                "returncode": result.returncode,
                "stdout_tail": result.stdout[-1000:] if result.stdout else "",
                "stderr_tail": result.stderr[-500:] if result.stderr else "",
            },
        }
    except subprocess.TimeoutExpired:
        return {
            "name": "test_suite",
            "score": 0.0,
            "details": {"error": f"Test suite timed out after {timeout}s"},
        }
    except Exception as e:
        return {
            "name": "test_suite",
            "score": 0.0,
            "details": {"error": str(e)},
        }


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
    evaluator_configs = {e["name"]: e for e in config.get("evaluators", [])}

    # 1. Run the project's own test suite (weight = 3.0, highest priority)
    test_command = config.get("tech_stack", {}).get("test_command", "")
    test_result = run_test_suite(test_command, repo_root)
    test_result["weight"] = 3.0
    results.append(test_result)

    # 2. Run each custom evaluator
    evaluators_dir = autoimprove_dir / "evaluators"
    if evaluators_dir.exists():
        for script_path in sorted(evaluators_dir.glob("*.py")):
            if script_path.name.startswith("_"):
                continue
            econf = evaluator_configs.get(script_path.stem, {})
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
    output = {
        "composite_score": round(composite, 6),
        "elapsed_seconds": round(elapsed, 1),
        "evaluators": results,
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
'''

# ---------------------------------------------------------------------------
# Evaluator script templates
#
# Each template is a complete, self-contained Python script with PEP 723
# inline metadata. They run via `uv run evaluators/<name>.py` and output
# a single JSON line: {"name": "...", "score": 0.0-1.0, "details": {...}}
# ---------------------------------------------------------------------------

EVALUATOR_TEMPLATES: dict[str, str] = {}

# --- Test suite evaluator ---
EVALUATOR_TEMPLATES["test_suite"] = '''\
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

# --- Python: code complexity (radon) ---
EVALUATOR_TEMPLATES["code_complexity_python"] = '''\
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "radon>=6.0",
# ]
# ///
"""
Code complexity evaluator for Python projects.
Measures average cyclomatic complexity using radon.

Score: 1.0 = low complexity (avg CC <= 5), 0.0 = high complexity (avg CC >= 25).
"""

import json
import os
import sys
from pathlib import Path

from radon.complexity import cc_visit


def find_python_files(root: Path) -> list[Path]:
    """Find all Python source files, skipping tests and venvs."""
    skip_dirs = {
        ".git", "__pycache__", ".venv", "venv", "node_modules",
        ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
        ".autoimprove", "tests", "test", ".eggs",
    }
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for f in filenames:
            if f.endswith(".py"):
                files.append(Path(dirpath) / f)
    return files


def main():
    root = Path(".")
    py_files = find_python_files(root)

    if not py_files:
        print(json.dumps({
            "name": "code_complexity",
            "score": 1.0,
            "details": {"info": "No Python source files found"},
        }))
        return

    total_complexity = 0
    total_blocks = 0
    file_details = {}

    for fpath in py_files:
        try:
            source = fpath.read_text(errors="replace")
            blocks = cc_visit(source)
            if blocks:
                avg = sum(b.complexity for b in blocks) / len(blocks)
                total_complexity += sum(b.complexity for b in blocks)
                total_blocks += len(blocks)
                file_details[str(fpath)] = {
                    "avg_complexity": round(avg, 2),
                    "num_blocks": len(blocks),
                    "max_complexity": max(b.complexity for b in blocks),
                }
        except Exception:
            pass

    if total_blocks == 0:
        avg_complexity = 0.0
    else:
        avg_complexity = total_complexity / total_blocks

    # Score: CC 1-5 = 1.0, CC 25+ = 0.0, linear interpolation
    score = max(0.0, min(1.0, 1.0 - (avg_complexity - 5) / 20))

    # Show worst files
    worst = sorted(file_details.items(), key=lambda x: -x[1]["avg_complexity"])[:5]

    print(json.dumps({
        "name": "code_complexity",
        "score": round(score, 4),
        "details": {
            "avg_complexity": round(avg_complexity, 2),
            "total_blocks": total_blocks,
            "total_files": len(py_files),
            "worst_files": dict(worst),
        },
    }))


if __name__ == "__main__":
    main()
'''

# --- Python: type coverage (mypy) ---
EVALUATOR_TEMPLATES["type_coverage_python"] = '''\
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "mypy>=1.0",
# ]
# ///
"""
Type annotation coverage evaluator for Python projects.
Uses mypy to check how many functions/methods have type annotations.

Score: fraction of functions with complete type annotations (0.0-1.0).
"""

import ast
import json
import os
import sys
from pathlib import Path


def find_python_files(root: Path) -> list[Path]:
    """Find all Python source files, skipping tests and venvs."""
    skip_dirs = {
        ".git", "__pycache__", ".venv", "venv", "node_modules",
        ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
        ".autoimprove", "tests", "test", ".eggs",
    }
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for f in filenames:
            if f.endswith(".py"):
                files.append(Path(dirpath) / f)
    return files


def check_annotations(fpath: Path) -> tuple[int, int]:
    """Count functions with and without return type annotations.

    Returns (annotated_count, total_count).
    """
    try:
        source = fpath.read_text(errors="replace")
        tree = ast.parse(source)
    except (SyntaxError, Exception):
        return 0, 0

    annotated = 0
    total = 0

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            total += 1
            # Check if return annotation exists
            has_return = node.returns is not None
            # Check if all args (except self/cls) have annotations
            args = node.args
            all_args = args.args + args.posonlyargs + args.kwonlyargs
            param_names_to_skip = {"self", "cls"}
            has_all_params = all(
                arg.annotation is not None
                for arg in all_args
                if arg.arg not in param_names_to_skip
            )
            if has_return and has_all_params:
                annotated += 1

    return annotated, total


def main():
    root = Path(".")
    py_files = find_python_files(root)

    if not py_files:
        print(json.dumps({
            "name": "type_coverage",
            "score": 1.0,
            "details": {"info": "No Python source files found"},
        }))
        return

    total_annotated = 0
    total_functions = 0

    for fpath in py_files:
        annotated, total = check_annotations(fpath)
        total_annotated += annotated
        total_functions += total

    if total_functions == 0:
        score = 1.0
    else:
        score = total_annotated / total_functions

    print(json.dumps({
        "name": "type_coverage",
        "score": round(score, 4),
        "details": {
            "annotated_functions": total_annotated,
            "total_functions": total_functions,
            "total_files": len(py_files),
        },
    }))


if __name__ == "__main__":
    main()
'''

# --- Python: lint score (ruff) ---
EVALUATOR_TEMPLATES["lint_python"] = '''\
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "ruff>=0.4.0",
# ]
# ///
"""
Lint score evaluator for Python projects.
Uses ruff to count lint violations and compute a quality score.

Score: 1.0 = no violations, decreases as violations increase.
"""

import json
import os
import subprocess
import sys
from pathlib import Path


def count_python_lines(root: Path) -> int:
    """Count total lines of Python source code."""
    skip_dirs = {
        ".git", "__pycache__", ".venv", "venv", "node_modules",
        ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
        ".autoimprove", "tests", "test", ".eggs",
    }
    total = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for f in filenames:
            if f.endswith(".py"):
                try:
                    total += len(Path(dirpath, f).read_text(errors="replace").splitlines())
                except OSError:
                    pass
    return total


def main():
    root = Path(".")

    try:
        result = subprocess.run(
            ["ruff", "check", ".", "--output-format=json", "--quiet"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(root),
        )
        # ruff outputs JSON array of violations
        try:
            violations = json.loads(result.stdout) if result.stdout.strip() else []
        except json.JSONDecodeError:
            violations = []

        num_violations = len(violations)
        total_lines = count_python_lines(root)

        if total_lines == 0:
            score = 1.0
        else:
            # Score: violations per 100 lines. 0 violations = 1.0, 10+ per 100 lines = 0.0
            violations_per_100 = (num_violations / total_lines) * 100
            score = max(0.0, min(1.0, 1.0 - violations_per_100 / 10))

        # Categorize violations
        categories: dict[str, int] = {}
        for v in violations:
            code = v.get("code", "unknown")
            categories[code] = categories.get(code, 0) + 1

        # Top violation types
        top_violations = sorted(categories.items(), key=lambda x: -x[1])[:10]

        print(json.dumps({
            "name": "lint_score",
            "score": round(score, 4),
            "details": {
                "num_violations": num_violations,
                "total_lines": total_lines,
                "violations_per_100_lines": round((num_violations / max(total_lines, 1)) * 100, 2),
                "top_violations": dict(top_violations),
            },
        }))

    except FileNotFoundError:
        print(json.dumps({
            "name": "lint_score",
            "score": 0.5,
            "details": {"error": "ruff not found, install with: pip install ruff"},
        }))
    except subprocess.TimeoutExpired:
        print(json.dumps({
            "name": "lint_score",
            "score": 0.0,
            "details": {"error": "ruff timed out after 120s"},
        }))
    except Exception as e:
        print(json.dumps({
            "name": "lint_score",
            "score": 0.0,
            "details": {"error": str(e)},
        }))


if __name__ == "__main__":
    main()
'''

# --- JavaScript/TypeScript: lint score (eslint) ---
EVALUATOR_TEMPLATES["lint_js"] = '''\
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Lint score evaluator for JavaScript/TypeScript projects.
Uses eslint (must be installed in the project) to count violations.

Score: 1.0 = no violations, decreases as violations increase.
"""

import json
import os
import subprocess
import sys
from pathlib import Path


def count_source_lines(root: Path) -> int:
    """Count total lines of JS/TS source code."""
    skip_dirs = {
        ".git", "node_modules", "dist", "build", ".next", ".nuxt",
        "coverage", ".autoimprove",
    }
    extensions = {".js", ".ts", ".jsx", ".tsx", ".mjs", ".mts"}
    total = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for f in filenames:
            if any(f.endswith(ext) for ext in extensions):
                try:
                    total += len(Path(dirpath, f).read_text(errors="replace").splitlines())
                except OSError:
                    pass
    return total


def main():
    root = Path(".")

    try:
        result = subprocess.run(
            ["npx", "eslint", ".", "--format=json", "--quiet"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(root),
        )
        try:
            data = json.loads(result.stdout) if result.stdout.strip() else []
        except json.JSONDecodeError:
            data = []

        total_errors = sum(f.get("errorCount", 0) for f in data)
        total_warnings = sum(f.get("warningCount", 0) for f in data)
        total_violations = total_errors + total_warnings
        total_lines = count_source_lines(root)

        if total_lines == 0:
            score = 1.0
        else:
            violations_per_100 = (total_violations / total_lines) * 100
            score = max(0.0, min(1.0, 1.0 - violations_per_100 / 10))

        print(json.dumps({
            "name": "lint_score",
            "score": round(score, 4),
            "details": {
                "errors": total_errors,
                "warnings": total_warnings,
                "total_violations": total_violations,
                "total_lines": total_lines,
            },
        }))

    except FileNotFoundError:
        print(json.dumps({
            "name": "lint_score",
            "score": 0.5,
            "details": {"error": "eslint not found (npx eslint)"},
        }))
    except subprocess.TimeoutExpired:
        print(json.dumps({
            "name": "lint_score",
            "score": 0.0,
            "details": {"error": "eslint timed out"},
        }))
    except Exception as e:
        print(json.dumps({
            "name": "lint_score",
            "score": 0.0,
            "details": {"error": str(e)},
        }))


if __name__ == "__main__":
    main()
'''

# --- Rust: clippy score ---
EVALUATOR_TEMPLATES["clippy_rust"] = '''\
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Clippy score evaluator for Rust projects.
Uses cargo clippy to count warnings and compute a quality score.

Score: 1.0 = no warnings, decreases as warnings increase.
"""

import json
import subprocess
import sys
from pathlib import Path


def main():
    root = Path(".")

    try:
        result = subprocess.run(
            ["cargo", "clippy", "--message-format=json", "--quiet"],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(root),
        )

        warnings = 0
        errors = 0
        for line in result.stdout.splitlines():
            try:
                msg = json.loads(line)
                if msg.get("reason") == "compiler-message":
                    level = msg.get("message", {}).get("level", "")
                    if level == "warning":
                        warnings += 1
                    elif level == "error":
                        errors += 1
            except json.JSONDecodeError:
                continue

        total = warnings + errors
        # Score: 0 issues = 1.0, 50+ issues = 0.0
        score = max(0.0, min(1.0, 1.0 - total / 50))

        print(json.dumps({
            "name": "clippy_score",
            "score": round(score, 4),
            "details": {
                "warnings": warnings,
                "errors": errors,
                "total_issues": total,
            },
        }))

    except FileNotFoundError:
        print(json.dumps({
            "name": "clippy_score",
            "score": 0.5,
            "details": {"error": "cargo not found"},
        }))
    except subprocess.TimeoutExpired:
        print(json.dumps({
            "name": "clippy_score",
            "score": 0.0,
            "details": {"error": "clippy timed out after 300s"},
        }))
    except Exception as e:
        print(json.dumps({
            "name": "clippy_score",
            "score": 0.0,
            "details": {"error": str(e)},
        }))


if __name__ == "__main__":
    main()
'''

# --- Go: vet score ---
EVALUATOR_TEMPLATES["vet_go"] = '''\
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Go vet score evaluator.
Uses go vet to check for suspicious constructs.

Score: 1.0 = no issues, 0.0 = issues found.
"""

import json
import subprocess
import sys
from pathlib import Path


def main():
    root = Path(".")

    try:
        result = subprocess.run(
            ["go", "vet", "./..."],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(root),
        )

        if result.returncode == 0:
            score = 1.0
            issues = 0
        else:
            # Count lines of vet output as issues
            issue_lines = [
                l for l in result.stderr.strip().splitlines()
                if l.strip() and not l.startswith("#")
            ]
            issues = len(issue_lines)
            # Score: 0 issues = 1.0, 20+ issues = 0.0
            score = max(0.0, min(1.0, 1.0 - issues / 20))

        print(json.dumps({
            "name": "vet_score",
            "score": round(score, 4),
            "details": {
                "issues": issues,
                "passed": result.returncode == 0,
            },
        }))

    except FileNotFoundError:
        print(json.dumps({
            "name": "vet_score",
            "score": 0.5,
            "details": {"error": "go not found"},
        }))
    except subprocess.TimeoutExpired:
        print(json.dumps({
            "name": "vet_score",
            "score": 0.0,
            "details": {"error": "go vet timed out"},
        }))
    except Exception as e:
        print(json.dumps({
            "name": "vet_score",
            "score": 0.0,
            "details": {"error": str(e)},
        }))


if __name__ == "__main__":
    main()
'''
