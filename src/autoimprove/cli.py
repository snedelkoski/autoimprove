"""CLI entry point for autoimprove.

Usage:
    autoimprove init <path>     Initialize a repo for self-improvement
    autoimprove status <path>   Show current improvement status
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from autoimprove import __version__
from autoimprove.config import (
    AUTOIMPROVE_DIR,
    RESULTS_FILE,
    load_config,
)


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@click.group()
@click.version_option(version=__version__, prog_name="autoimprove")
def main():
    """Universal autonomous self-improvement for any software repo.

    Analyzes a repository, generates evaluation harnesses, and produces
    a program.md that guides an AI coding agent through an infinite
    improvement loop.

    Inspired by karpathy/autoresearch — but for ANY repo, not just ML training.

    Usage:
        1. Run: autoimprove init ./my-repo
        2. Tell your coding agent: "read .autoimprove/program.md and start improving"
    """
    pass


@main.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option("--force", is_flag=True, help="Overwrite existing .autoimprove/ directory")
@click.option("-v", "--verbose", is_flag=True, help="Verbose output")
def init(path: str, force: bool, verbose: bool):
    """Initialize a repository for autonomous self-improvement.

    Analyzes the repo at PATH, detects its tech stack, generates evaluation
    harnesses, and creates the .autoimprove/ directory with all necessary artifacts.

    No API keys or LLM setup needed — all detection is heuristic-based.
    The coding agent refines the artifacts with its own intelligence.

    Examples:

        autoimprove init ./my-project

        autoimprove init /path/to/repo --force
    """
    _setup_logging(verbose)

    repo_path = Path(path).resolve()

    try:
        from autoimprove.initializer import initialize_repo
        initialize_repo(repo_path, force=force)
    except FileExistsError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@main.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, dir_okay=True))
def status(path: str):
    """Show current improvement status for a repo.

    Displays experiment history, scores, and progress for the repo at PATH.

    Examples:

        autoimprove status ./my-project
    """
    _setup_logging(False)

    repo_path = Path(path).resolve()
    ai_dir = repo_path / AUTOIMPROVE_DIR

    if not ai_dir.exists():
        click.echo(f"Not initialized. Run 'autoimprove init {repo_path}' first.")
        sys.exit(1)

    try:
        config = load_config(repo_path)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Load baseline
    from autoimprove.evaluator import load_baseline
    baseline = load_baseline(repo_path)

    # Read results
    results_path = ai_dir / RESULTS_FILE
    if results_path.exists():
        lines = results_path.read_text().strip().splitlines()
        experiments = lines[1:] if len(lines) > 1 else []
    else:
        experiments = []

    # Parse results
    kept = sum(1 for e in experiments if "\tkeep\t" in e)
    discarded = sum(1 for e in experiments if "\tdiscard\t" in e)
    crashed = sum(1 for e in experiments if "\tcrash\t" in e)

    click.echo(f"Repository: {repo_path}")
    click.echo(f"Tech stack: {', '.join(config.tech_stack.languages)} | "
               f"{', '.join(config.tech_stack.frameworks)}")
    click.echo(f"Test command: {config.tech_stack.test_command or '(none)'}")
    click.echo(f"Evaluators: {len(config.evaluators)}")
    click.echo(f"Mutable patterns: {', '.join(config.file_classification.mutable_patterns)}")
    click.echo()

    if baseline:
        click.echo(f"Baseline score: {baseline.get('composite_score', 0):.6f}")
    else:
        click.echo("Baseline: not yet established")

    click.echo(f"Experiments: {len(experiments)} total "
               f"({kept} kept, {discarded} discarded, {crashed} crashed)")

    if experiments:
        click.echo("\nRecent experiments:")
        for exp in experiments[-10:]:
            click.echo(f"  {exp}")

    # Show best score from results
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
            click.echo(f"\nBest score: {best_score:.6f} ({improvement:+.1f}% vs baseline)")


if __name__ == "__main__":
    main()
