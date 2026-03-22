"""The instruction document for autoimprove.

This is the entire product. When `autoimprove init` runs, it writes this
document into .autoimprove/INSTRUCTIONS.md. A coding agent reads it, analyzes
the repository, and creates all the artifacts needed for autonomous
self-improvement.

No templates, no heuristics, no LLM API calls. The agent IS the intelligence.
"""

INSTRUCTIONS_MD = """\
# autoimprove

You are setting up an autonomous self-improvement program for **{repo_name}**.

This document tells you how to analyze the repository, build an evaluation
system, write the improvement program, and run the loop. Follow it
sequentially — each phase produces artifacts the next phase depends on.

**Experiment time budget: {experiment_duration} seconds.**
Every evaluator that runs the project's core functionality (training, benchmarks,
integration tests, etc.) must complete within this budget. This makes experiments
comparable — just like autoresearch's fixed 5-minute training window.

---

## Phase 1 — Understand the Repository

Read these files (skip any that don't exist):

1. `README.md` / `README.rst` — what the project does, how to use it.
2. `AGENTS.md` / `CLAUDE.md` / `CURSORRULES` / `.github/copilot-instructions.md` — \
developer guidelines, architecture notes, conventions. These are gold — they tell you \
what the maintainers care about.
3. The main config file — `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, \
`Gemfile`, `pom.xml`, `build.gradle`. This tells you the language, dependencies, \
build commands, and test setup.
4. Browse the source tree. For every source file, note its name and purpose in one line.

After reading, answer these questions (write the answers into `.autoimprove/analysis.md` \
so you can reference them later):

- **What does this project do?** One paragraph.
- **What is the project's primary success metric?** This is the single most important \
question. What does "better" mean for this specific project? Examples:
  - ML training repo → lower validation loss or higher benchmark accuracy
  - API server → faster response times, higher correctness rate
  - Compiler / interpreter → correctness on a test suite of programs, compilation speed
  - CLI tool → correctness of output, performance on representative inputs
  - Library / SDK → test pass rate, API coverage, documentation completeness
  - Game / simulation → score, framerate, convergence speed

  Be specific. "Better code quality" is not a primary metric. "val_bpb on the \
WikiText-103 validation set" is. "Percentage of TabArena benchmarks where the model \
beats XGBoost" is. The primary metric must be something you can **measure with a \
script** and express as a **float in [0.0, 1.0]** (higher = better).
- **File map**: every source file with a one-line description. Example:
  ```
  model.py        — Transformer architecture + sklearn-compatible wrappers
  train.py        — Training loop (offline HDF5 or online generation)
  generate_data.py — SCM-based synthetic data generation
  evaluate.py     — Evaluation: sklearn quick-eval + TabArena benchmark
  ```
- **Tech stack**: language, framework, package manager, test runner.
- **How to build**: exact shell command (e.g. `cargo build`, `npm run build`, or "N/A").
- **How to test**: exact shell command (e.g. `uv run pytest`, `npm test`).
- **How to run**: exact shell command if applicable.
- **How to evaluate the primary metric**: exact shell command and expected output format. \
If no evaluation script exists yet, describe what one would need to do.
- **Editable files**: which files contain the core logic the agent should improve. \
List them explicitly by name — not glob patterns. If there are many (>20), group by \
directory.
- **Fixed files**: which files must NOT be modified — tests, CI, configs, lock files, \
`.autoimprove/` itself. Be explicit.
- **Current quality issues**: what you observe — missing tests, type annotation gaps, \
lint violations, high complexity functions, dead code, poor error handling, etc.

---

## Phase 2 — Design the Evaluation System

You need two things: individual **evaluator scripts** and an **eval harness** that runs \
them all and computes a composite score.

### 2a. The Primary Evaluator — What Actually Matters

**This is the most important evaluator.** It measures the project's primary success \
metric — the one you identified in Phase 1. Every other evaluator is supplementary.

Think of it like autoresearch's `prepare.py`: it runs the project's core functionality \
and produces a single number that captures whether the project got better or worse. \
The primary evaluator should:

1. **Run the project's actual workload** — train a model, serve requests, compile \
programs, process inputs — whatever the project *does*.
2. **Respect the time budget** — complete within {experiment_duration} seconds. If the \
full workload takes longer, run a representative subset (e.g., train for \
{experiment_duration}s instead of the full run, benchmark on 10 datasets instead of \
100, test on 50 programs instead of 500).
3. **Produce a score in [0.0, 1.0]** — higher is better. Normalize appropriately:
   - For loss metrics: `score = max(0, 1 - loss / baseline_loss)` or use a sigmoid.
   - For accuracy metrics: use directly if already in [0, 1].
   - For pass rates: `score = n_passed / n_total`.
   - For speed metrics: `score = min(1.0, target_time / actual_time)`.
4. **Have the highest weight** — typically 3.0–5.0, dominating the composite score.

**Examples by project type:**

| Project type | Primary evaluator | What it does | Score formula |
|---|---|---|---|
| ML training | `val_loss` | Trains for {experiment_duration}s, reports validation loss | `max(0, 1 - val_loss / baseline_val_loss)` |
| ML benchmark | `benchmark_score` | Runs eval suite with time cap | `mean_accuracy` across datasets |
| API server | `api_correctness` | Sends test requests, checks responses | `n_correct / n_total` |
| Compiler | `correctness` | Compiles + runs test programs | `n_passing / n_total` |
| CLI tool | `output_correctness` | Runs on reference inputs, diffs output | `n_matching / n_total` |
| Library | `test_pass_rate` | Runs the project's test suite | `n_passed / n_total` |
| Data pipeline | `output_quality` | Runs pipeline on sample data, checks output | domain-specific |

If this project is a library where the test suite IS the primary metric, that's fine — \
`test_suite` can be both the primary evaluator and the most heavily weighted one. But \
make that decision consciously after analyzing what the project does, not by default.

### 2b. Supplementary Evaluators

Create additional evaluator scripts for code quality dimensions. These catch regressions \
and encourage clean code, but they should NOT dominate the composite score.

| Evaluator | What it measures | Typical weight | When to use |
|-----------|-----------------|---------------|-------------|
| `test_suite` | Test pass rate | 2.0 | Always (if tests exist or should exist) |
| `lint` | Linter violations (ruff, eslint, clippy) | 1.0 | Always |
| `type_coverage` | Type annotation completeness | 0.5 | Typed languages |
| `complexity` | Cyclomatic complexity | 0.5 | Large codebases |
| `test_coverage` | Line/branch coverage | 1.0 | If coverage tooling exists |
| `build` | Clean build with no warnings | 1.5 | Compiled languages |
| `doc_coverage` | Docstring/JSDoc coverage | 0.5 | Libraries/APIs |

**Weight guidelines**: The primary evaluator should have the highest weight — typically \
2–5x any supplementary evaluator. If the primary evaluator is `test_suite` (e.g., for a \
library), give it weight 3.0+ and keep supplementary evaluators at 0.5–1.5. An evaluator \
that can be gamed trivially (e.g. adding `# type: ignore` everywhere) should have a \
lower weight.

### 2c. Evaluator Script Requirements

Create self-contained Python scripts in `.autoimprove/evaluators/`. Each one measures \
one dimension.

**Requirements for every evaluator script:**

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["<any-deps>"]
# ///
\"\"\"<What this evaluator measures>.\"\"\"

# ... measurement logic ...

# MUST print exactly one JSON line to stdout:
print(json.dumps({{
    "name": "<evaluator_name>",
    "score": 0.0,  # float in [0.0, 1.0] — higher is better
    "details": {{   # arbitrary dict with diagnostic info
        "violations": 3,
        "files_checked": 12,
        # ... anything useful for the agent to understand the score
    }},
}}))
```

- Use [PEP 723](https://peps.python.org/pep-0723/) inline metadata so they run \
standalone via `uv run .autoimprove/evaluators/<name>.py`.
- Each script MUST be independent — no imports from the project, no shared state.
- Output exactly one JSON line. Nothing else on stdout.
- Exit 0 on success. Non-zero exit = score 0.0.
- **Time budget**: evaluators that run the project's core workload (training, benchmarks, \
integration tests) MUST complete within {experiment_duration} seconds. Use timeouts, \
iteration caps, or dataset subsampling to enforce this. Code quality evaluators (lint, \
type coverage) are typically fast and don't need explicit time caps.

### 2d. Eval Harness

Create `.autoimprove/eval_harness.py` — the master evaluation script. It:

1. Discovers all `*.py` files in `.autoimprove/evaluators/` (skip `_`-prefixed files).
2. Runs each via `uv run .autoimprove/evaluators/<name>.py` with a timeout.
3. Parses the JSON output line.
4. Computes a weighted-average composite score.
5. Prints the final result as JSON to stdout.

**Reference implementation** (adapt as needed):

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
\"\"\"
autoimprove eval harness — runs all evaluators, computes composite score.
DO NOT MODIFY after baseline is established.

Usage: uv run .autoimprove/eval_harness.py
\"\"\"

import json
import subprocess
import time
from pathlib import Path


def run_evaluator(script: Path, cwd: Path, timeout: int = {experiment_duration}) -> dict:
    try:
        r = subprocess.run(
            ["uv", "run", str(script)],
            capture_output=True, text=True, timeout=timeout, cwd=str(cwd),
        )
        if r.returncode != 0:
            return {{"name": script.stem, "score": 0.0,
                    "details": {{"error": f"exit {{r.returncode}}",
                               "stderr": r.stderr[-500:]}}}}
        for line in reversed(r.stdout.strip().splitlines()):
            if line.strip().startswith("{{"):
                return json.loads(line)
        return {{"name": script.stem, "score": 0.0,
                "details": {{"error": "no JSON output"}}}}
    except subprocess.TimeoutExpired:
        return {{"name": script.stem, "score": 0.0,
                "details": {{"error": f"timeout after {{timeout}}s"}}}}
    except Exception as e:
        return {{"name": script.stem, "score": 0.0,
                "details": {{"error": str(e)}}}}


def main():
    here = Path(__file__).resolve().parent
    repo = here.parent
    evaluators_dir = here / "evaluators"

    # Load weights from config if it exists, else default to 1.0
    config_path = here / "config.yaml"
    weights = {{}}
    if config_path.exists():
        import yaml  # only needed if config exists
        with open(config_path) as f:
            cfg = yaml.safe_load(f) or {{}}
        for e in cfg.get("evaluators", []):
            weights[e["name"]] = e.get("weight", 1.0)

    t0 = time.time()
    results = []
    for script in sorted(evaluators_dir.glob("*.py")):
        if script.name.startswith("_"):
            continue
        r = run_evaluator(script, repo)
        r["weight"] = weights.get(r["name"], 1.0)
        results.append(r)

    total_w = sum(r["weight"] for r in results)
    composite = sum(r["score"] * r["weight"] for r in results) / total_w if total_w else 0.0

    print(json.dumps({{
        "composite_score": round(composite, 6),
        "elapsed_seconds": round(time.time() - t0, 1),
        "evaluators": results,
    }}, indent=2))


if __name__ == "__main__":
    main()
```

You may modify this reference implementation to fit the project. For example, if the \
project has a long-running benchmark, increase the timeout. If you want to print a \
human-readable summary in addition to JSON, add it to stderr (not stdout).

**Important:** Once you establish the baseline, the eval harness becomes fixed — do not \
modify it during the improvement loop. It is the "ground truth" (like `prepare.py` in \
autoresearch). If you modify it, you invalidate all previous scores.

---

## Phase 3 — Write `program.md`

Create `.autoimprove/program.md` — the document the agent reads at the start of each \
improvement session. This is the most important artifact. It must be **specific to this \
repository**, not generic.

### What makes a great program.md

Study this example from [karpathy/autoresearch](https://github.com/karpathy/autoresearch). \
Notice how every detail is concrete:

- Files are named explicitly: "Read `prepare.py` — fixed constants... `train.py` — \
the file you modify."
- Commands are exact: `uv run train.py > run.log 2>&1`
- Output format is shown verbatim: the `val_bpb: 0.997900` block
- Strategy is specific: "A 0.001 val_bpb improvement that adds 20 lines of hacky code? \
Probably not worth it."
- The TSV schema has real example rows with real-looking values.
- There is a **fixed time budget** — 5 minutes per experiment — making all runs comparable.

Your program.md must have this level of specificity. **Never use glob patterns when you \
can list files by name. Never use placeholder values when you can use real baseline \
numbers. Never describe a command abstractly when you can write the exact shell line.**

### Required sections

**1. Setup** — Step-by-step checklist for starting a new session:
- Create branch `autoimprove/<tag>` (tag = today's date, e.g. `jun15`)
- Read specific files (list them by name with one-line descriptions)
- Verify baseline exists
- Confirm and go

**2. Scope** — What the agent can and cannot modify:
- "What you CAN do" — list the editable files by name. For each file, one line saying \
what it contains and what kind of changes are fair game.
- "What you CANNOT do" — list protected files/dirs. Explain why (tests are ground truth, \
configs control the build, .autoimprove/ is the evaluation system).

**3. Evaluation** — How to run the eval and what the output looks like:
- The exact command: `uv run .autoimprove/eval_harness.py`
- The exact output format (paste the actual baseline JSON, or a representative example)
- What each evaluator measures, its weight, and its current baseline score
- **The primary metric**: which evaluator measures what actually matters, and why
- **Time budget**: each evaluation run completes within {experiment_duration} seconds
- A quick command to extract just the composite score from the log

**4. The Experiment Loop** — The infinite loop, step by step:
```
LOOP FOREVER:
1. Pick a focused improvement (one idea per experiment)
2. Edit the code
3. git commit -m "experiment: <description>"
4. Run: uv run .autoimprove/eval_harness.py > .autoimprove/run.log 2>&1
5. Read: cat .autoimprove/run.log (or extract composite_score)
6. If crashed: read the error, try to fix, or abandon
7. Log to results.tsv
8. If improved: keep the commit, update baseline
9. If not improved: git reset --hard HEAD~1
10. GOTO 1

Time budget: {experiment_duration} seconds per evaluation run.
Each experiment must be evaluable within this window.
```

**5. Logging** — The results.tsv format:
- Tab-separated, NOT comma-separated
- Columns: `commit`, `composite_score`, `status`, `description`
- Include 3-4 example rows with realistic values from this project's baseline

**6. Strategy** — Prioritized improvement ideas based on the baseline:
- **Start with the primary metric.** If the project trains a model and the baseline \
val_loss evaluator scores 0.3, improving model architecture or training loop is higher \
impact than adding type annotations.
- Look at which evaluator has the most room for improvement AND the highest weight — \
that's where to focus first.
- Include specific targets: "Add return type annotations to these 12 functions in \
model.py" is better than "improve type coverage."
- The simplicity criterion: "All else equal, simpler is better. Removing code and \
getting equal or better results is a great outcome."
- Crash recovery: "If it's a typo, fix and re-run. If the idea is broken, log crash \
and move on."

**7. NEVER STOP** — The autonomy doctrine:
```
Once the loop begins, do NOT pause to ask the human if you should continue.
Do NOT ask "should I keep going?" or "is this a good stopping point?".
The human might be asleep. You are autonomous. If you run out of ideas,
think harder — re-read the source code, try combining previous experiments,
try more radical approaches. The loop runs until the human interrupts you.
```

---

## Phase 4 — Write `config.yaml`

Create `.autoimprove/config.yaml` with the project metadata and evaluator configuration. \
The eval harness reads this for evaluator weights.

```yaml
version: "1.0"
repo: {repo_name}
summary: "<one-line project description>"
experiment_duration_seconds: {experiment_duration}

tech_stack:
  language: "<primary language>"
  framework: "<primary framework or 'none'>"
  package_manager: "<uv/npm/cargo/etc.>"
  test_command: "<exact test command>"
  build_command: "<exact build command or 'none'>"

editable_files:
  - "<file1.ext>  # one-line description"
  - "<file2.ext>  # one-line description"

protected_paths:
  - "tests/"
  - ".autoimprove/"
  - "<other protected paths>"

primary_metric:
  name: "<evaluator_name>"
  description: "<what the project's primary success metric is>"

evaluators:
  - name: "<primary_evaluator_name>"
    description: "<what it measures — the primary metric>"
    weight: <float — highest weight, typically 3.0-5.0>
    timeout: {experiment_duration}
  - name: "<supplementary_evaluator>"
    description: "<what it measures>"
    weight: <float — lower than primary, typically 0.5-2.0>
    timeout: <seconds>
```

---

## Phase 5 — Establish Baseline and Begin

1. Run the evaluation:
   ```bash
   uv run .autoimprove/eval_harness.py
   ```
2. Save the output to `.autoimprove/baselines/baseline.json`.
3. Record the baseline in `.autoimprove/results.tsv`:
   ```
   baseline\\t<composite_score>\\tkeep\\tbaseline — initial state
   ```
4. Go back to `program.md` and fill in the actual baseline scores everywhere you left \
placeholders.
5. Read your own `program.md` and start the improvement loop.

---

## Checklist

Before starting the improvement loop, verify:

- [ ] `.autoimprove/analysis.md` exists with your repo analysis
- [ ] `.autoimprove/analysis.md` identifies the **primary success metric** for this project
- [ ] `.autoimprove/evaluators/` has a **primary evaluator** that measures what actually \
matters
- [ ] `.autoimprove/evaluators/` has supplementary evaluators for code quality
- [ ] `.autoimprove/eval_harness.py` exists and runs successfully
- [ ] `.autoimprove/config.yaml` exists with evaluator weights (primary evaluator has \
highest weight)
- [ ] `.autoimprove/program.md` exists with all sections filled in
- [ ] `.autoimprove/baselines/baseline.json` exists with real scores
- [ ] `.autoimprove/results.tsv` has the header row and baseline entry
- [ ] `program.md` contains actual baseline numbers, not placeholders
- [ ] Primary evaluator completes within {experiment_duration} seconds

Everything ready? Read `program.md` and begin.
"""
