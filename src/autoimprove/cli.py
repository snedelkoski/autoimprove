"""CLI entry point for autoimprove.

Usage:
    autoimprove init <path>     Initialize a repo for self-improvement
    autoimprove run <path>      Start the autonomous improvement loop
    autoimprove status <path>   Show current improvement status
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from autoimprove import __version__
from autoimprove.config import LLMConfig


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

    Analyzes a repository, generates evaluation harnesses, and runs an
    autonomous improvement loop powered by LLMs.

    Inspired by karpathy/autoresearch — but for ANY repo, not just ML training.
    """
    pass


@main.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option("--force", is_flag=True, help="Overwrite existing .autoimprove/ directory")
@click.option("--model", default=None, help="LLM model to use (default: claude-opus-4-20250514)")
@click.option("--base-url", default=None, help="LLM API base URL")
@click.option("--api-key", default=None, help="LLM API key (or set ANTHROPIC_API_KEY / OPENAI_API_KEY)")
@click.option("-v", "--verbose", is_flag=True, help="Verbose output")
def init(
    path: str,
    force: bool,
    model: str | None,
    base_url: str | None,
    api_key: str | None,
    verbose: bool,
):
    """Initialize a repository for autonomous self-improvement.

    Analyzes the repo at PATH, detects its tech stack, generates evaluation
    harnesses, and creates the .autoimprove/ directory with all necessary artifacts.

    Examples:

        autoimprove init ./my-project

        autoimprove init /path/to/repo --model gpt-4o --force
    """
    _setup_logging(verbose)

    # Build LLM config from CLI options
    llm_config = LLMConfig()
    if model:
        llm_config.model = model
    if base_url:
        llm_config.base_url = base_url
    if api_key:
        llm_config.api_key = api_key

    repo_path = Path(path).resolve()

    try:
        from autoimprove.initializer import initialize_repo
        initialize_repo(repo_path, llm_config=llm_config, force=force)
    except FileExistsError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        click.echo("Set ANTHROPIC_API_KEY or OPENAI_API_KEY environment variable.", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@main.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option("--max-experiments", "-n", type=int, default=None,
              help="Max number of experiments (default: infinite)")
@click.option("--model", default=None, help="Override LLM model from config")
@click.option("--base-url", default=None, help="Override LLM API base URL from config")
@click.option("--api-key", default=None, help="Override LLM API key from config")
@click.option("-v", "--verbose", is_flag=True, help="Verbose output")
def run(
    path: str,
    max_experiments: int | None,
    model: str | None,
    base_url: str | None,
    api_key: str | None,
    verbose: bool,
):
    """Start the autonomous improvement loop.

    Reads the .autoimprove/ configuration from PATH and begins the experiment
    loop: propose change -> apply -> evaluate -> keep/discard -> repeat.

    The loop runs indefinitely until stopped with Ctrl+C (or until --max-experiments
    is reached).

    Examples:

        autoimprove run ./my-project

        autoimprove run ./my-project -n 10

        ANTHROPIC_API_KEY=sk-... autoimprove run ./my-project
    """
    _setup_logging(verbose)

    repo_path = Path(path).resolve()

    # Load and optionally override config
    try:
        from autoimprove.config import load_config

        config = load_config(repo_path)

        # Apply CLI overrides
        if model:
            config.llm.model = model
        if base_url:
            config.llm.base_url = base_url
        if api_key:
            config.llm.api_key = api_key

        # Re-save with overrides (so runner picks them up)
        from autoimprove.config import get_config_path
        config.save(get_config_path(repo_path))

    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    try:
        from autoimprove.runner import run_improvement_loop
        run_improvement_loop(repo_path, max_experiments=max_experiments)
    except KeyboardInterrupt:
        pass  # runner handles this gracefully
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

    try:
        from autoimprove.runner import show_status
        show_status(repo_path)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
