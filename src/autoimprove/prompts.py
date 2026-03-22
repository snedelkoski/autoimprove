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

### 2a. Evaluator Scripts

Create self-contained Python scripts in `.autoimprove/evaluators/`. Each one measures \
one dimension of code quality.

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

**Choose evaluators relevant to this project.** Common ones:

| Evaluator | What it measures | Typical weight | When to use |
|-----------|-----------------|---------------|-------------|
| `test_suite` | Test pass rate | 3.0 | Always (if tests exist or should exist) |
| `lint` | Linter violations (ruff, eslint, clippy) | 1.5 | Always |
| `type_coverage` | Type annotation completeness | 1.0 | Typed languages |
| `complexity` | Cyclomatic complexity | 1.0 | Large codebases |
| `test_coverage` | Line/branch coverage | 2.0 | If coverage tooling exists |
| `build` | Clean build with no warnings | 2.0 | Compiled languages |
| `benchmark` | Performance on project's own benchmarks | 3.0 | If benchmarks exist |
| `doc_coverage` | Docstring/JSDoc coverage | 0.5 | Libraries/APIs |

You don't have to use these exact names or definitions. **Design evaluators that \
capture what actually matters for this specific project.** An ML training repo might \
have a `val_loss` evaluator. An API might have a `response_time` evaluator. A compiler \
might have a `correctness` evaluator that runs a test suite of programs.

**Weight guidelines**: The test suite should usually be the highest weight. An evaluator \
that can be gamed trivially (e.g. just adding `# type: ignore` everywhere to "fix" type \
errors) should have a lower weight. Evaluators that measure real correctness or \
performance should be weighted highest.

### 2b. Eval Harness

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


def run_evaluator(script: Path, cwd: Path, timeout: int = 120) -> dict:
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
```

**5. Logging** — The results.tsv format:
- Tab-separated, NOT comma-separated
- Columns: `commit`, `composite_score`, `status`, `description`
- Include 3-4 example rows with realistic values from this project's baseline

**6. Strategy** — Prioritized improvement ideas based on the baseline:
- Start with the highest-impact items. If tests score 0.0, that's #1.
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

evaluators:
  - name: "<evaluator_name>"
    description: "<what it measures>"
    weight: <float>
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
- [ ] `.autoimprove/evaluators/` has at least one evaluator script
- [ ] `.autoimprove/eval_harness.py` exists and runs successfully
- [ ] `.autoimprove/config.yaml` exists with evaluator weights
- [ ] `.autoimprove/program.md` exists with all sections filled in
- [ ] `.autoimprove/baselines/baseline.json` exists with real scores
- [ ] `.autoimprove/results.tsv` has the header row and baseline entry
- [ ] `program.md` contains actual baseline numbers, not placeholders

Everything ready? Read `program.md` and begin.
"""
