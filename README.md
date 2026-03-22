# autoimprove

Autonomous self-improvement for any software repo.

Inspired by [karpathy/autoresearch](https://github.com/karpathy/autoresearch) — generalized to work with **any** repository.

## How it works

autoimprove creates an instruction document that tells a coding agent how to:

1. **Analyze** the repository — understand its structure, tech stack, quality issues
2. **Design evaluation** — write evaluator scripts and an eval harness specific to the project
3. **Write program.md** — a detailed, repo-specific improvement program (like karpathy's `program.md`)
4. **Run the loop** — autonomously experiment, evaluate, keep/discard, repeat forever

The key insight: **the agent does the thinking, not the tool.** autoimprove doesn't try to detect your tech stack with heuristics or generate evaluators from templates. It writes one great instruction document, and your coding agent — which is a frontier LLM — handles the rest with its own intelligence.

```
autoimprove init ./my-repo
  └── creates .autoimprove/INSTRUCTIONS.md

agent reads INSTRUCTIONS.md
  └── analyzes repo, writes program.md, evaluators, config
  └── runs the improvement loop forever
```

## Quick start

```bash
# Install
uv tool install autoimprove

# Initialize
autoimprove init ./my-project

# Hand off to your coding agent (Claude Code, OpenCode, Copilot, etc.)
# Tell it: "read .autoimprove/INSTRUCTIONS.md and set up the improvement program"

# Check progress
autoimprove status ./my-project
```

No API keys. No LLM configuration. No heuristics. Just one instruction document.

## What `init` creates

```
.autoimprove/
  INSTRUCTIONS.md   # The agent reads this — detailed setup guide
  results.tsv       # Experiment log (header row only)
  evaluators/       # Empty — agent creates evaluator scripts here
  baselines/        # Empty — agent saves baseline here
  experiments/      # Empty — workspace
```

That's it. The agent then creates:

- `program.md` — the improvement program (specific to this repo)
- `config.yaml` — tech stack and evaluator weights
- `eval_harness.py` — the evaluation runner
- `evaluators/*.py` — individual evaluator scripts
- `baselines/baseline.json` — initial scores
- `analysis.md` — repo analysis notes

## Design philosophy

| autoresearch | autoimprove |
|---|---|
| Human writes `program.md` by hand | Agent writes `program.md` guided by `INSTRUCTIONS.md` |
| Human writes `prepare.py` (eval) | Agent writes eval harness + evaluators |
| Fixed domain (ML training) | Any software domain |
| Human decides what's editable | Agent decides what's editable |

The common thread: **the evaluation system is tamper-proof.** Once the baseline is established, the agent cannot modify the eval harness or evaluators — only the source code under improvement.

## Commands

### `autoimprove init <path>`

Create `.autoimprove/` scaffold with `INSTRUCTIONS.md`.

```bash
autoimprove init ./my-project           # first time
autoimprove init ./my-project --force   # overwrite existing
```

### `autoimprove status <path>`

Show improvement progress — setup state, baseline scores, experiment history.

```bash
autoimprove status ./my-project
```

## Project structure

```
src/autoimprove/
  __init__.py      — version
  cli.py           — Click CLI: init, status
  config.py        — Constants and helpers for status command
  prompts.py       — INSTRUCTIONS.md content (the core product)
  initializer.py   — Creates scaffold and writes INSTRUCTIONS.md
  analyzer.py      — Stub (analysis is now agent-driven)
  evaluator.py     — Re-exports for backwards compat
```

## Dependencies

Minimal by design: `click`, `pyyaml`. No pydantic, no LLM libraries, no network calls.

## License

MIT
