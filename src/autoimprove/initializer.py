"""Initializer for autoimprove.

Creates the .autoimprove/ directory scaffold and writes INSTRUCTIONS.md.
That's it. The coding agent does the rest.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from autoimprove.config import (
    AUTOIMPROVE_DIR,
    BASELINE_DIR,
    EVALUATORS_DIR,
    EXPERIMENTS_DIR,
    INSTRUCTIONS_FILE,
    RESULTS_FILE,
)
from autoimprove.prompts import INSTRUCTIONS_MD

logger = logging.getLogger(__name__)


def initialize_repo(repo_path: Path, force: bool = False) -> None:
    """Initialize a repository for autoimprove.

    Creates the .autoimprove/ directory with:
    - INSTRUCTIONS.md — the agent reads this to set everything up
    - evaluators/ — empty, agent populates
    - baselines/ — empty, agent populates
    - experiments/ — empty workspace
    - results.tsv — header row only

    Args:
        repo_path: Path to the target repository root.
        force: If True, overwrite existing .autoimprove/ directory.
    """
    repo_path = repo_path.resolve()
    ai_dir = repo_path / AUTOIMPROVE_DIR

    if ai_dir.exists() and not force:
        raise FileExistsError(
            f"{ai_dir} already exists. Use --force to overwrite."
        )

    if not repo_path.is_dir():
        raise NotADirectoryError(f"Not a directory: {repo_path}")

    # Wipe old directory completely when --force is used
    if ai_dir.exists() and force:
        shutil.rmtree(ai_dir)

    # Create directory structure
    for subdir in [EVALUATORS_DIR, EXPERIMENTS_DIR, BASELINE_DIR]:
        (ai_dir / subdir).mkdir(parents=True, exist_ok=True)

    # Write INSTRUCTIONS.md
    instructions = INSTRUCTIONS_MD.format(repo_name=repo_path.name)
    (ai_dir / INSTRUCTIONS_FILE).write_text(instructions)

    # Write results.tsv header
    (ai_dir / RESULTS_FILE).write_text(
        "experiment\tcomposite_score\tstatus\tdescription\n"
    )

    print(f"\nCreated {ai_dir}/")
    print(f"\nNext step: tell your coding agent to read "
          f".autoimprove/{INSTRUCTIONS_FILE} and set up the improvement program.")
