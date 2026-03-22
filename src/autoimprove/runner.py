"""Autonomous improvement loop for autoimprove.

This is the core engine — analogous to the experiment loop in autoresearch's program.md.
It proposes experiments via LLM, applies changes, evaluates, and keeps/discards.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import git

from autoimprove.config import (
    AUTOIMPROVE_DIR,
    EXPERIMENTS_DIR,
    PROGRAM_FILE,
    RESULTS_FILE,
    ProjectConfig,
    load_config,
)
from autoimprove.evaluator import (
    EvalResult,
    compare_to_baseline,
    load_baseline,
    run_evaluation,
    save_baseline,
)
from autoimprove.llm import LLMClient
from autoimprove.prompts import (
    PROPOSE_EXPERIMENT_SYSTEM,
    PROPOSE_EXPERIMENT_USER,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_program_md(repo_path: Path) -> str:
    """Read the program.md instruction file."""
    program_path = repo_path / AUTOIMPROVE_DIR / PROGRAM_FILE
    if not program_path.exists():
        return "(No program.md found)"
    return program_path.read_text()


def _read_results_tsv(repo_path: Path, max_lines: int = 50) -> str:
    """Read recent experiment history from results.tsv."""
    results_path = repo_path / AUTOIMPROVE_DIR / RESULTS_FILE
    if not results_path.exists():
        return "(No experiment history)"
    lines = results_path.read_text().strip().splitlines()
    if len(lines) <= 1:
        return "(No experiments yet — this is the first run)"
    # Return header + last N experiments
    header = lines[0]
    recent = lines[max(1, len(lines) - max_lines):]
    return "\n".join([header] + recent)


def _read_mutable_files(repo_path: Path, config: ProjectConfig) -> str:
    """Read all mutable files and format them for the LLM prompt."""
    parts = []
    patterns = config.file_classification.mutable_patterns

    for pattern in patterns:
        for fpath in sorted(repo_path.glob(pattern)):
            if fpath.is_file() and AUTOIMPROVE_DIR not in str(fpath):
                rel = fpath.relative_to(repo_path)
                try:
                    content = fpath.read_text(errors="replace")
                    # Cap at 10K chars per file to avoid prompt blowout
                    if len(content) > 10000:
                        content = content[:10000] + "\n... (truncated)"
                    parts.append(f"### {rel}\n```\n{content}\n```\n")
                except (OSError, UnicodeDecodeError):
                    parts.append(f"### {rel}\n(Could not read file)\n")

    if not parts:
        return "(No mutable files found matching patterns)"

    return "\n".join(parts)


def _is_mutable(file_path: str, config: ProjectConfig) -> bool:
    """Check if a file path matches any mutable pattern."""
    for pattern in config.file_classification.mutable_patterns:
        if fnmatch(file_path, pattern):
            return True
    return False


def _log_experiment(
    repo_path: Path,
    exp_id: str,
    composite_score: float,
    status: str,
    description: str,
) -> None:
    """Append an experiment result to results.tsv."""
    results_path = repo_path / AUTOIMPROVE_DIR / RESULTS_FILE
    line = f"{exp_id}\t{composite_score:.6f}\t{status}\t{description}\n"
    with open(results_path, "a") as f:
        f.write(line)


def _save_experiment_artifacts(
    repo_path: Path,
    exp_id: str,
    proposal: dict[str, Any],
    result: EvalResult,
    status: str,
) -> None:
    """Save experiment artifacts (proposal, metrics, etc.)."""
    exp_dir = repo_path / AUTOIMPROVE_DIR / EXPERIMENTS_DIR / exp_id
    exp_dir.mkdir(parents=True, exist_ok=True)

    # Save proposal (without full file contents to save space)
    proposal_summary = {k: v for k, v in proposal.items() if k != "changes"}
    proposal_summary["files_changed"] = [
        c.get("file", "unknown") for c in proposal.get("changes", [])
    ]
    (exp_dir / "proposal.json").write_text(json.dumps(proposal_summary, indent=2))

    # Save metrics
    metrics = result.to_dict()
    metrics["status"] = status
    (exp_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))


# ---------------------------------------------------------------------------
# Shadow copy management
# ---------------------------------------------------------------------------

def _create_shadow_copies(repo_path: Path, files: list[str], exp_id: str) -> Path:
    """Create shadow copies of files before modifying them.

    Returns the directory containing the shadow copies.
    """
    shadow_dir = repo_path / AUTOIMPROVE_DIR / EXPERIMENTS_DIR / exp_id / "shadow"
    shadow_dir.mkdir(parents=True, exist_ok=True)

    for rel_path in files:
        src = repo_path / rel_path
        if src.exists():
            dst = shadow_dir / rel_path
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    return shadow_dir


def _restore_from_shadow(repo_path: Path, shadow_dir: Path, files: list[str]) -> None:
    """Restore files from shadow copies."""
    for rel_path in files:
        shadow_file = shadow_dir / rel_path
        target_file = repo_path / rel_path
        if shadow_file.exists():
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(shadow_file, target_file)
        elif target_file.exists():
            # File was newly created by the experiment — remove it
            target_file.unlink()


# ---------------------------------------------------------------------------
# Main improvement loop
# ---------------------------------------------------------------------------

def run_improvement_loop(
    repo_path: Path,
    max_experiments: int | None = None,
) -> None:
    """Run the autonomous improvement loop.

    This is the main entry point for `autoimprove run`. It loops indefinitely
    (or up to max_experiments), proposing and evaluating experiments.

    Args:
        repo_path: Path to the target repository root.
        max_experiments: Optional limit on number of experiments. None = infinite.
    """
    repo_path = repo_path.resolve()
    config = load_config(repo_path)
    llm = LLMClient(config.llm)

    # Initialize git repo object
    try:
        repo = git.Repo(repo_path)
    except git.InvalidGitRepositoryError:
        print(f"WARNING: {repo_path} is not a git repository. "
              "Git branching/revert will be disabled.")
        repo = None

    # Create experiment branch
    branch_name = f"{config.branch_prefix}/{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if repo:
        try:
            repo.git.checkout("-b", branch_name)
            print(f"Created branch: {branch_name}")
        except git.GitCommandError:
            print(f"WARNING: Could not create branch {branch_name}. "
                  "Continuing on current branch.")

    # Load baseline
    baseline = load_baseline(repo_path)
    if baseline:
        print(f"Baseline composite score: {baseline.get('composite_score', 0):.6f}")
    else:
        print("No baseline found. First experiment will establish baseline.")
        print("Running baseline evaluation...")
        baseline_result = run_evaluation(repo_path, config)
        if baseline_result.success:
            save_baseline(repo_path, baseline_result)
            baseline = baseline_result.to_dict()
            print(f"Baseline established: {baseline_result.composite_score:.6f}")
        else:
            print(f"WARNING: Baseline eval failed: {baseline_result.error}")
            print("Continuing anyway — experiments will be compared against score 0.0")

    experiment_count = 0
    kept_count = 0
    discarded_count = 0
    crash_count = 0

    print("\n" + "=" * 60)
    print("AUTONOMOUS IMPROVEMENT LOOP STARTED")
    print("Press Ctrl+C to stop")
    print("=" * 60 + "\n")

    try:
        while True:
            if max_experiments is not None and experiment_count >= max_experiments:
                print(f"\nReached max experiments ({max_experiments}). Stopping.")
                break

            experiment_count += 1
            exp_id = f"exp_{experiment_count:04d}"
            print(f"\n--- Experiment {exp_id} ---")

            # 1. Propose an experiment
            print("  Proposing experiment...")
            try:
                proposal = _propose_experiment(repo_path, config, llm, baseline)
            except Exception as e:
                logger.error("Failed to propose experiment: %s", e)
                print(f"  ERROR: Failed to propose experiment: {e}")
                crash_count += 1
                _log_experiment(repo_path, exp_id, 0.0, "crash",
                               f"Failed to propose: {str(e)[:100]}")
                time.sleep(5)  # back off
                continue

            title = proposal.get("title", "Untitled experiment")
            print(f"  Title: {title}")
            print(f"  Hypothesis: {proposal.get('hypothesis', 'N/A')[:100]}")

            changes = proposal.get("changes", [])
            if not changes:
                print("  SKIP: No changes proposed.")
                _log_experiment(repo_path, exp_id, 0.0, "skip", "No changes proposed")
                continue

            # Validate changes are only to mutable files
            changed_files = [c["file"] for c in changes]
            for f in changed_files:
                if not _is_mutable(f, config):
                    print(f"  REJECT: Proposed change to protected file: {f}")
                    _log_experiment(repo_path, exp_id, 0.0, "reject",
                                   f"Proposed change to protected file: {f}")
                    continue

            # 2. Create shadow copies
            shadow_dir = _create_shadow_copies(repo_path, changed_files, exp_id)

            # 3. Apply changes
            print(f"  Applying {len(changes)} file change(s)...")
            try:
                for change in changes:
                    fpath = repo_path / change["file"]
                    action = change.get("action", "modify")
                    if action == "delete":
                        if fpath.exists():
                            fpath.unlink()
                    else:
                        fpath.parent.mkdir(parents=True, exist_ok=True)
                        fpath.write_text(change["new_content"])
            except Exception as e:
                print(f"  ERROR applying changes: {e}")
                _restore_from_shadow(repo_path, shadow_dir, changed_files)
                crash_count += 1
                _log_experiment(repo_path, exp_id, 0.0, "crash",
                               f"Apply failed: {str(e)[:100]}")
                continue

            # 4. Evaluate
            print("  Running evaluation...")
            eval_result = run_evaluation(repo_path, config)

            if not eval_result.success:
                print(f"  CRASH: {eval_result.error}")
                # Try to fix — retry up to max_fix_retries times
                fixed = False
                for retry in range(config.max_fix_retries):
                    print(f"  Retry {retry + 1}/{config.max_fix_retries}...")
                    # For now, just revert and skip. Advanced: ask LLM to fix.
                    break

                if not fixed:
                    _restore_from_shadow(repo_path, shadow_dir, changed_files)
                    crash_count += 1
                    _log_experiment(repo_path, exp_id, 0.0, "crash",
                                   f"{title}: {(eval_result.error or '')[:80]}")
                    _save_experiment_artifacts(repo_path, exp_id, proposal,
                                              eval_result, "crash")
                    continue

            # 5. Compare to baseline
            improved, delta = compare_to_baseline(eval_result, baseline)
            print(f"  Score: {eval_result.composite_score:.6f} "
                  f"(delta: {delta:+.6f})")
            print(f"  {eval_result.summary()}")

            if improved:
                # KEEP the change
                print(f"  KEEP (improved by {delta:+.6f})")
                kept_count += 1
                status = "keep"

                # Update baseline
                save_baseline(repo_path, eval_result)
                baseline = eval_result.to_dict()

                # Git commit if available
                if repo:
                    try:
                        repo.git.add("-A")
                        repo.git.commit("-m", f"autoimprove: {title}")
                    except git.GitCommandError as e:
                        logger.warning("Git commit failed: %s", e)

            else:
                # DISCARD the change
                print(f"  DISCARD (delta: {delta:+.6f})")
                discarded_count += 1
                status = "discard"

                # Revert
                _restore_from_shadow(repo_path, shadow_dir, changed_files)

            _log_experiment(repo_path, exp_id, eval_result.composite_score,
                           status, title)
            _save_experiment_artifacts(repo_path, exp_id, proposal,
                                      eval_result, status)

            # Progress summary
            total = kept_count + discarded_count + crash_count
            print(f"\n  Progress: {total} experiments "
                  f"({kept_count} kept, {discarded_count} discarded, "
                  f"{crash_count} crashed)")
            if baseline:
                print(f"  Current best: {baseline.get('composite_score', 0):.6f}")

    except KeyboardInterrupt:
        print("\n\nStopped by user (Ctrl+C)")
    finally:
        # Print final summary
        print("\n" + "=" * 60)
        print("EXPERIMENT LOOP FINISHED")
        print(f"  Total experiments: {experiment_count}")
        print(f"  Kept: {kept_count}")
        print(f"  Discarded: {discarded_count}")
        print(f"  Crashed: {crash_count}")
        if baseline:
            print(f"  Final best score: {baseline.get('composite_score', 0):.6f}")
        print("=" * 60)


# ---------------------------------------------------------------------------
# Experiment proposal
# ---------------------------------------------------------------------------

def _propose_experiment(
    repo_path: Path,
    config: ProjectConfig,
    llm: LLMClient,
    baseline: dict[str, Any] | None,
) -> dict[str, Any]:
    """Use the LLM to propose an experiment.

    Returns a dict with:
    - title: str
    - hypothesis: str
    - changes: list[dict] with file, action, description, new_content
    - risk_level: str
    - expected_improvement: str
    """
    program_md = _read_program_md(repo_path)
    mutable_content = _read_mutable_files(repo_path, config)
    history = _read_results_tsv(repo_path)

    if baseline:
        current_scores = json.dumps(baseline, indent=2)
    else:
        current_scores = "(No baseline yet — this is the first experiment)"

    user_prompt = PROPOSE_EXPERIMENT_USER.format(
        program_md=program_md,
        mutable_files_content=mutable_content,
        experiment_history=history,
        current_scores=current_scores,
    )

    proposal = llm.analyze_json(
        PROPOSE_EXPERIMENT_SYSTEM,
        user_prompt,
        temperature=0.7,
        max_tokens=8192,
    )

    return proposal


# ---------------------------------------------------------------------------
# Status display
# ---------------------------------------------------------------------------

def show_status(repo_path: Path) -> None:
    """Display current autoimprove status for a repo."""
    repo_path = repo_path.resolve()
    ai_dir = repo_path / AUTOIMPROVE_DIR

    if not ai_dir.exists():
        print(f"Not initialized. Run 'autoimprove init {repo_path}' first.")
        return

    config = load_config(repo_path)

    # Load baseline
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

    print(f"Repository: {repo_path}")
    print(f"Tech stack: {', '.join(config.tech_stack.languages)} | "
          f"{', '.join(config.tech_stack.frameworks)}")
    print(f"Test command: {config.tech_stack.test_command or '(none)'}")
    print(f"Evaluators: {len(config.evaluators)}")
    print(f"Mutable patterns: {', '.join(config.file_classification.mutable_patterns)}")
    print()

    if baseline:
        print(f"Baseline score: {baseline.get('composite_score', 0):.6f}")
    else:
        print("Baseline: not yet established")

    print(f"Experiments: {len(experiments)} total "
          f"({kept} kept, {discarded} discarded, {crashed} crashed)")

    if experiments:
        print("\nRecent experiments:")
        for exp in experiments[-10:]:
            print(f"  {exp}")

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
            print(f"\nBest score: {best_score:.6f} ({improvement:+.1f}% vs baseline)")
