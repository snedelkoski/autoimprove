# autoimprove

Universal autonomous self-improvement for any software repo.

Inspired by [karpathy/autoresearch](https://github.com/karpathy/autoresearch) — but generalized to work with **any** repository: APIs, web services, microservices, infrastructure, ML training, CLI tools, libraries — literally anything.

## How it works

autoimprove takes the core pattern from autoresearch — where an AI agent autonomously experiments on code, evaluates results, and keeps improvements — and generalizes it:

| autoresearch | autoimprove |
|-------------|------------|
| Single domain (ML training) | Any software domain |
| Fixed eval metric (val_bpb) | Auto-discovered multi-metric evaluation |
| Single mutable file (train.py) | Auto-detected mutable surface area |
| Manual program.md | Auto-generated program.md (still human-editable) |
| Requires specific GPU setup | Runs anywhere |

**Key design principle:** autoimprove makes **no LLM API calls**. It is designed to be used **inside AI coding agents** (Claude Code, OpenCode, GitHub Copilot). The agent IS the LLM. All repo analysis is heuristic-based — the agent supplements with its own intelligence.

### The self-improvement loop

```
LOOP FOREVER:
  1. Agent reads program.md for strategy + experiment history
  2. Agent proposes a focused experiment (a code change)
  3. Agent modifies files within the mutable surface area
  4. Agent runs evaluation harness → gets composite score
  5. If score improved → keep (commit, update baseline)
  6. If score worse → discard (git revert)
  7. Log to results.tsv
  8. Repeat (never stop, never ask)
```

## Installation

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install autoimprove as a tool
uv tool install autoimprove

# Or run directly without installing
uvx autoimprove --help
```

## Quick start

```bash
# 1. Initialize your repo for self-improvement
autoimprove init ./my-project

# 2. (Optional) Edit .autoimprove/program.md to customize agent behavior

# 3. Tell your coding agent to start the loop
#    In Claude Code, OpenCode, Copilot, etc.:
#    "Read .autoimprove/program.md and start improving"

# 4. Check progress
autoimprove status ./my-project
```

No API keys needed. No LLM configuration. Just `init` and hand off to your coding agent.

## What `init` does

When you run `autoimprove init`, it:

1. **Analyzes** your repo heuristically — detects language, framework, build system, test setup from file extensions, config files (pyproject.toml, package.json, Cargo.toml, go.mod), and lock files
2. **Classifies files** into mutable (core source) vs protected (tests, config, CI, docs)
3. **Discovers evaluation metrics** beyond your existing tests — code complexity, type coverage, lint score, and more depending on tech stack
4. **Selects evaluator templates** from a built-in library based on detected stack
5. **Generates** `.autoimprove/` with:
   - `config.yaml` — detected tech stack, file classification, evaluator configs
   - `program.md` — agent instruction file (human-editable)
   - `eval_harness.py` — fixed evaluation entry point
   - `evaluators/*.py` — evaluator scripts with PEP 723 inline metadata (run via `uv run`)
   - `results.tsv` — experiment log
   - `baselines/baseline.json` — baseline scores
   - `experiments/` — experiment workspace
6. **Runs baseline** evaluation and saves initial scores

### Supported tech stacks

| Language | Detection | Evaluators |
|----------|-----------|------------|
| Python | pyproject.toml, setup.py, requirements.txt | test_suite, code_complexity, type_coverage, lint (ruff) |
| JavaScript/TypeScript | package.json | test_suite, lint (eslint) |
| Rust | Cargo.toml | test_suite, clippy |
| Go | go.mod | test_suite, vet |
| Java | pom.xml, build.gradle | test_suite |
| Ruby | Gemfile | test_suite |

Additional languages and evaluators are detected from file extensions and build tools.

## Commands

### `autoimprove init <path>`

Initialize a repo for self-improvement. Creates `.autoimprove/` directory with all artifacts.

```bash
autoimprove init ./my-project           # first time
autoimprove init ./my-project --force   # overwrite existing
autoimprove init ./my-project -v        # verbose output
```

### `autoimprove status <path>`

Show improvement status — baseline scores, experiment history, progress.

```bash
autoimprove status ./my-project
```

## Editing program.md

The `program.md` file in `.autoimprove/` is your control surface. Edit it to:

- Focus the agent on specific improvement areas
- Set constraints (e.g., "don't increase memory usage")
- Adjust experiment strategy
- Add domain-specific context

The agent reads this file at the start of each experiment iteration.

## Generated `.autoimprove/` structure

```
.autoimprove/
  config.yaml          # Tech stack, mutable/protected patterns, evaluator configs
  program.md           # Agent instructions (the experiment loop)
  eval_harness.py      # Fixed eval runner (runs all evaluators, outputs JSON)
  results.tsv          # Experiment log (TSV)
  evaluators/          # Individual evaluator scripts (PEP 723, run via uv run)
    test_suite.py
    code_complexity.py
    type_coverage.py
    lint_score.py
  baselines/
    baseline.json      # Baseline evaluation scores
  experiments/         # Experiment workspace
```

## Project structure

```
src/autoimprove/
  __init__.py      — version
  cli.py           — Click CLI: init, status
  config.py        — Pydantic config models
  prompts.py       — Templates: program.md, eval harness, evaluator scripts
  analyzer.py      — Heuristic repo analysis (tech stack, file classification)
  initializer.py   — Generates .autoimprove/ artifacts
  evaluator.py     — Evaluation scoring + baseline comparison
```

## Dependencies

Minimal by design:

- `click` — CLI framework
- `pydantic` — config validation
- `pyyaml` — config serialization

No LLM client libraries. No API keys. No network calls.

## License

MIT
