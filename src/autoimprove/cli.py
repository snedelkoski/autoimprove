"""CLI entry point for autoimprove.

Usage:
    autoimprove init <path>     Scaffold .autoimprove/ with INSTRUCTIONS.md
    autoimprove status <path>   Show improvement progress
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from autoimprove import __version__
from autoimprove.config import (
    AUTOIMPROVE_DIR,
    DEFAULT_EXPERIMENT_DURATION,
    INSTRUCTIONS_FILE,
    RESULTS_FILE,
    load_baseline,
    load_config,
)


@click.group()
@click.version_option(version=__version__, prog_name="autoimprove")
def main():
    """Autonomous self-improvement for any software repo.

    Creates an instruction document that a coding agent reads to analyze
    your repository, design evaluation metrics, and run an infinite
    improvement loop.

    Inspired by karpathy/autoresearch — generalized to any codebase.

    Usage:
        1. autoimprove init ./my-repo
        2. Tell your coding agent: "read .autoimprove/INSTRUCTIONS.md and
           set up the improvement program"
    """
    pass


@main.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option(
    "--force", is_flag=True, help="Overwrite existing .autoimprove/ directory"
)
@click.option(
    "--duration",
    type=int,
    default=DEFAULT_EXPERIMENT_DURATION,
    show_default=True,
    help="Experiment time budget in seconds. Evaluators that run the project's core "
    "workload (training, benchmarks, etc.) must complete within this window.",
)
def init(path: str, force: bool, duration: int):
    """Initialize a repository for autonomous self-improvement.

    Creates .autoimprove/ with INSTRUCTIONS.md — a detailed guide for your
    coding agent to analyze the repo, design evaluators, write program.md,
    and run the improvement loop.

    No API keys, no LLM calls, no heuristics. The agent does the thinking.

    Examples:

        autoimprove init ./my-project

        autoimprove init /path/to/repo --force

        autoimprove init ./ml-repo --duration 600
    """
    repo_path = Path(path).resolve()

    try:
        from autoimprove.initializer import initialize_repo

        initialize_repo(repo_path, force=force, duration=duration)
    except FileExistsError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, dir_okay=True))
def status(path: str):
    """Show current improvement status for a repo.

    Reads results.tsv, baseline, and config to display progress.

    Examples:

        autoimprove status ./my-project
    """
    repo_path = Path(path).resolve()
    ai_dir = repo_path / AUTOIMPROVE_DIR

    if not ai_dir.exists():
        click.echo(f"Not initialized. Run 'autoimprove init {repo_path}' first.")
        sys.exit(1)

    # Check what artifacts exist
    has_instructions = (ai_dir / INSTRUCTIONS_FILE).exists()
    has_program = (ai_dir / "program.md").exists()
    has_config = (ai_dir / "config.yaml").exists()
    has_evaluators = (ai_dir / "evaluators").exists() and any(
        (ai_dir / "evaluators").glob("*.py")
    )

    config = load_config(repo_path)
    baseline = load_baseline(repo_path)

    # Read results
    results_path = ai_dir / RESULTS_FILE
    experiments: list[str] = []
    if results_path.exists():
        lines = results_path.read_text().strip().splitlines()
        experiments = lines[1:] if len(lines) > 1 else []

    # Display status
    click.echo(f"Repository: {repo_path}")
    click.echo()

    # Setup progress
    click.echo("Setup:")
    click.echo(f"  INSTRUCTIONS.md: {'yes' if has_instructions else 'no'}")
    click.echo(f"  program.md:      {'yes' if has_program else 'not yet'}")
    click.echo(f"  config.yaml:     {'yes' if has_config else 'not yet'}")
    click.echo(f"  evaluators:      {'yes' if has_evaluators else 'not yet'}")

    if config:
        summary = config.get("summary", "")
        tech = config.get("tech_stack", {})
        lang = tech.get("language", "")
        if summary:
            click.echo(f"\n  Summary: {summary}")
        if lang:
            click.echo(f"  Language: {lang}")

    click.echo()

    if baseline:
        click.echo(f"Baseline score: {baseline.get('composite_score', 0):.6f}")
        evaluators = baseline.get("evaluators", [])
        for ev in evaluators:
            name = ev.get("name", "?")
            score = ev.get("score", 0)
            weight = ev.get("weight", 1.0)
            click.echo(f"  {name}: {score:.4f} (weight={weight})")
    else:
        click.echo("Baseline: not yet established")

    # Parse experiment results
    kept = sum(1 for e in experiments if "\tkeep\t" in e)
    discarded = sum(1 for e in experiments if "\tdiscard\t" in e)
    crashed = sum(1 for e in experiments if "\tcrash\t" in e)

    click.echo(
        f"\nExperiments: {len(experiments)} total "
        f"({kept} kept, {discarded} discarded, {crashed} crashed)"
    )

    if experiments:
        click.echo("\nRecent experiments:")
        for exp in experiments[-10:]:
            click.echo(f"  {exp}")

    # Best score
    best_score = 0.0
    for exp in experiments:
        parts = exp.split("\t")
        if len(parts) >= 2:
            try:
                score = float(parts[1])
                best_score = max(best_score, score)
            except ValueError:
                pass

    if best_score > 0 and baseline:
        baseline_score = baseline.get("composite_score", 0)
        if baseline_score > 0:
            improvement = ((best_score - baseline_score) / baseline_score) * 100
            click.echo(
                f"\nBest score: {best_score:.6f} ({improvement:+.1f}% vs baseline)"
            )


if __name__ == "__main__":
    main()
