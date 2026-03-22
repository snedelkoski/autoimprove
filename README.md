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
| Direct file edits | Shadow copies + git branches |
| Requires specific GPU | Runs anywhere |

### The self-improvement loop

```
LOOP FOREVER:
  1. LLM reads program.md for strategy + experiment history
  2. LLM proposes a focused experiment (a code change)
  3. Shadow-copy originals, apply changes
  4. Run evaluation harness (tests + custom evaluators)
  5. If score improved → keep (commit, update baseline)
  6. If score worse → discard (restore from shadow)
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

# 3. Start the autonomous improvement loop
ANTHROPIC_API_KEY=sk-... autoimprove run ./my-project

# 4. Check progress
autoimprove status ./my-project
```

## What `init` does

When you run `autoimprove init`, it:

1. **Analyzes** your repo using an LLM — detects language, framework, build system, test setup
2. **Classifies files** into mutable (core source) vs protected (tests, config, CI)
3. **Discovers evaluation metrics** beyond your existing tests — code complexity, type coverage, duplication, security, etc.
4. **Generates** `.autoimprove/` with:
   - `config.yaml` — detected settings
   - `program.md` — agent instruction file (human-editable)
   - `eval_harness.py` — fixed evaluation entry point
   - `evaluators/*.py` — custom evaluator scripts
   - `results.tsv` — experiment log
5. **Runs baseline** evaluation and saves scores

## What `run` does

The `run` command starts the autonomous improvement loop:

- Creates a git branch (`autoimprove/<timestamp>`)
- LLM proposes experiments based on program.md, current code, and history
- Changes are applied with shadow copies (originals are never corrupted)
- Evaluation harness runs all evaluators and computes composite score
- Improvements are kept (committed), regressions are discarded (reverted)
- Everything is logged to `results.tsv`
- Runs indefinitely until Ctrl+C

## Configuration

### LLM Provider

autoimprove uses an OpenAI-compatible API. Default: Claude Opus 4.6 via Anthropic.

```bash
# Anthropic (default)
ANTHROPIC_API_KEY=sk-... autoimprove run ./my-project

# OpenAI
OPENAI_API_KEY=sk-... autoimprove run ./my-project --model gpt-4o --base-url https://api.openai.com/v1

# Local model (e.g., ollama)
OPENAI_BASE_URL=http://localhost:11434/v1 OPENAI_API_KEY=ollama autoimprove run ./my-project --model llama3
```

### Editing program.md

The `program.md` file in `.autoimprove/` is your control surface. Edit it to:

- Focus the agent on specific improvement areas
- Set constraints (e.g., "don't increase memory usage")
- Adjust experiment strategy
- Add domain-specific context

## Project structure

```
src/autoimprove/
  __init__.py      — version
  cli.py           — Click CLI: init, run, status
  config.py        — Pydantic config models
  llm.py           — OpenAI-compatible LLM client
  prompts.py       — All LLM prompt templates
  analyzer.py      — Repo analysis (tech stack, file classification)
  initializer.py   — Generates .autoimprove/ artifacts
  evaluator.py     — Evaluation orchestration + scoring
  runner.py        — The autonomous improvement loop
```

## License

MIT
