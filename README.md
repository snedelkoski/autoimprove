# autoimprove

Autonomous self-improvement for any software repo.

Inspired by [karpathy/autoresearch](https://github.com/karpathy/autoresearch), generalized to work with any repository.

## Install

```bash
uv tool install autoimprove
```

## Usage

```bash
# 1. Initialize your repo
autoimprove init ./my-project

# 2. Open a coding agent (Claude Code, OpenCode, Copilot, Cursor, ...)
# 3. Tell it:
```

> Read `.autoimprove/INSTRUCTIONS.md` and execute all phases.

The agent analyzes your repo, writes evaluators, establishes a baseline, and starts an autonomous improvement loop — experimenting, evaluating, keeping what works, reverting what doesn't.

You can optionally review `program.md` after the agent writes it (Phase 3) to check the improvement plan before it starts running experiments.

```bash
# Check progress anytime
autoimprove status ./my-project
```

## How it works

autoimprove creates a single file — `.autoimprove/INSTRUCTIONS.md` — that tells the agent what to do. The agent does all the thinking: it figures out your tech stack, decides what "better" means for your project, writes evaluation scripts, and runs the loop.

```
autoimprove init ./my-repo
  └── .autoimprove/INSTRUCTIONS.md

agent reads INSTRUCTIONS.md
  ├── analyzes repo, picks a primary metric
  ├── writes evaluators + eval harness
  ├── writes program.md (improvement plan)
  ├── establishes baseline scores
  └── runs the experiment loop forever
        experiment → evaluate → keep or revert → repeat
```

Each experiment is a git commit. Results are logged to `.autoimprove/results.tsv`.

## Options

```bash
autoimprove init ./my-repo --duration 600   # time budget per experiment in seconds (default: 300)
autoimprove init ./my-repo --force          # overwrite existing .autoimprove/
```

## License

MIT
