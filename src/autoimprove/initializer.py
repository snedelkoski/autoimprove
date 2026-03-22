"""Initializer for autoimprove.

Generates the .autoimprove/ directory inside a target repo with all necessary
artifacts: config, program.md, eval harness, custom evaluators, and baselines.

All detection is heuristic-based — no LLM calls required. The coding agent
that runs this tool can refine the generated artifacts afterwards.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from autoimprove.analyzer import (
    classify_files,
    detect_tech_stack,
    discover_evaluators,
)
from autoimprove.config import (
    AUTOIMPROVE_DIR,
    BASELINE_DIR,
    BASELINE_FILE,
    CONFIG_FILE,
    EVAL_HARNESS_FILE,
    EVALUATORS_DIR,
    EXPERIMENTS_DIR,
    PROGRAM_FILE,
    RESULTS_FILE,
    EvaluatorConfig,
    ProjectConfig,
)
from autoimprove.prompts import (
    EVAL_HARNESS_TEMPLATE,
    EVALUATOR_TEMPLATES,
    PROGRAM_MD_TEMPLATE,
)

logger = logging.getLogger(__name__)


def initialize_repo(
    repo_path: Path,
    force: bool = False,
) -> ProjectConfig:
    """Initialize a repository for autoimprove.

    This is the main entry point for `autoimprove init`. It:
    1. Heuristically detects the tech stack
    2. Classifies files into mutable/protected
    3. Discovers relevant evaluators from the template library
    4. Generates .autoimprove/ with all artifacts
    5. Runs baseline evaluation

    Args:
        repo_path: Path to the target repository root.
        force: If True, overwrite existing .autoimprove/ directory.

    Returns:
        The generated ProjectConfig.
    """
    repo_path = repo_path.resolve()
    ai_dir = repo_path / AUTOIMPROVE_DIR

    if ai_dir.exists() and not force:
        raise FileExistsError(
            f"{ai_dir} already exists. Use --force to overwrite."
        )

    if not repo_path.is_dir():
        raise NotADirectoryError(f"Not a directory: {repo_path}")

    # --- Step 1: Detect tech stack ---
    print("Analyzing repository...")
    tech_stack, repo_summary = detect_tech_stack(repo_path)

    print(f"  Languages: {', '.join(tech_stack.languages) or '(none detected)'}")
    print(f"  Frameworks: {', '.join(tech_stack.frameworks) or '(none detected)'}")
    print(f"  Package manager: {tech_stack.package_manager or '(none detected)'}")
    print(f"  Test command: {tech_stack.test_command or '(none detected)'}")

    # --- Step 2: Classify files ---
    file_classification = classify_files(repo_path, tech_stack)
    print(f"  Mutable patterns: {', '.join(file_classification.mutable_patterns[:5])}"
          f"{'...' if len(file_classification.mutable_patterns) > 5 else ''}")

    # --- Step 3: Discover evaluators ---
    print("\nSelecting evaluators...")
    evaluator_defs = discover_evaluators(repo_path, tech_stack)
    print(f"  Selected {len(evaluator_defs)} evaluators:")
    for edef in evaluator_defs:
        print(f"    - {edef['name']}: {edef.get('description', '')}")

    # --- Step 4: Create .autoimprove/ directory ---
    print("\nGenerating .autoimprove/ artifacts...")
    _create_directory_structure(ai_dir)

    # Build evaluator configs
    evaluator_configs = []
    for edef in evaluator_defs:
        script_name = f"{edef['name']}.py"
        evaluator_configs.append(EvaluatorConfig(
            name=edef["name"],
            description=edef.get("description", ""),
            script=script_name,
            weight=edef.get("weight", 1.0),
            timeout=edef.get("timeout", 120),
        ))

    # Build and save config
    config = ProjectConfig(
        repo_path=str(repo_path),
        repo_summary=repo_summary,
        tech_stack=tech_stack,
        file_classification=file_classification,
        evaluators=evaluator_configs,
    )
    config_path = ai_dir / CONFIG_FILE
    config.save(config_path)
    print(f"  Created {CONFIG_FILE}")

    # Write evaluator scripts from templates
    evaluators_dir = ai_dir / EVALUATORS_DIR
    for edef in evaluator_defs:
        template_key = edef.get("template_key", "")
        template = EVALUATOR_TEMPLATES.get(template_key, "")
        if template:
            script_name = f"{edef['name']}.py"
            script_path = evaluators_dir / script_name
            template_vars = edef.get("template_vars", {})
            if template_vars:
                script_content = template.format(**template_vars)
            else:
                script_content = template
            script_path.write_text(script_content)
            script_path.chmod(0o755)
    print(f"  Created {len(evaluator_defs)} evaluator scripts")

    # Write eval harness
    harness_path = ai_dir / EVAL_HARNESS_FILE
    harness_path.write_text(EVAL_HARNESS_TEMPLATE)
    harness_path.chmod(0o755)
    print(f"  Created {EVAL_HARNESS_FILE}")

    # Generate program.md from template
    program_md = _generate_program_md(
        repo_path=repo_path,
        repo_summary=repo_summary,
        tech_stack=tech_stack,
        file_classification=file_classification,
        evaluator_configs=evaluator_configs,
    )
    program_path = ai_dir / PROGRAM_FILE
    program_path.write_text(program_md)
    print(f"  Created {PROGRAM_FILE}")

    # Initialize results.tsv with header
    results_path = ai_dir / RESULTS_FILE
    results_path.write_text("experiment\tcomposite_score\tstatus\tdescription\n")
    print(f"  Created {RESULTS_FILE}")

    # --- Step 5: Run baseline evaluation ---
    print("\nRunning baseline evaluation...")
    baseline = _run_baseline(repo_path, ai_dir)
    if baseline:
        baseline_path = ai_dir / BASELINE_DIR / BASELINE_FILE
        baseline_path.write_text(json.dumps(baseline, indent=2))
        composite = baseline.get("composite_score", 0)
        print(f"  Baseline composite score: {composite:.4f}")
        n_evals = len(baseline.get("evaluators", []))
        print(f"  {n_evals} evaluators ran successfully")
    else:
        print("  WARNING: Baseline evaluation failed. You may need to fix evaluator scripts.")

    print(f"\nInitialization complete! Files are in {ai_dir}/")
    print(f"\nNext step: read .autoimprove/{PROGRAM_FILE} and start improving!")

    return config


def _create_directory_structure(ai_dir: Path) -> None:
    """Create the .autoimprove/ directory structure."""
    for subdir in [EVALUATORS_DIR, EXPERIMENTS_DIR, BASELINE_DIR]:
        (ai_dir / subdir).mkdir(parents=True, exist_ok=True)


def _generate_program_md(
    repo_path: Path,
    repo_summary: str,
    tech_stack: Any,
    file_classification: Any,
    evaluator_configs: list[EvaluatorConfig],
) -> str:
    """Generate the program.md agent instruction file from template."""
    evaluator_descriptions = "\n".join(
        f"- **{e.name}** (weight={e.weight}): {e.description}"
        for e in evaluator_configs
    )

    mutable_patterns_list = "\n".join(
        f"  - `{p}`" for p in file_classification.mutable_patterns
    ) or "  - (no mutable patterns detected — you may need to configure this)"

    protected_patterns_list = "\n".join(
        f"  - `{p}`" for p in file_classification.protected_patterns[:15]
    )
    if len(file_classification.protected_patterns) > 15:
        protected_patterns_list += f"\n  - ... and {len(file_classification.protected_patterns) - 15} more"

    return PROGRAM_MD_TEMPLATE.format(
        repo_name=repo_path.name,
        repo_summary=repo_summary,
        languages=", ".join(tech_stack.languages) or "(none detected)",
        frameworks=", ".join(tech_stack.frameworks) or "(none detected)",
        package_manager=tech_stack.package_manager or "(none detected)",
        build_system=tech_stack.build_system or "(none detected)",
        test_framework=tech_stack.test_framework or "(none detected)",
        test_command=tech_stack.test_command or "(none detected)",
        build_command=tech_stack.build_command or "(none)",
        run_command=tech_stack.run_command or "(none)",
        mutable_patterns_list=mutable_patterns_list,
        protected_patterns_list=protected_patterns_list,
        evaluator_descriptions=evaluator_descriptions or "- (no evaluators configured)",
    )


def _run_baseline(repo_path: Path, ai_dir: Path) -> dict[str, Any] | None:
    """Run the eval harness and return baseline metrics."""
    harness_path = ai_dir / EVAL_HARNESS_FILE
    try:
        result = subprocess.run(
            ["uv", "run", str(harness_path)],
            capture_output=True,
            text=True,
            timeout=600,
            cwd=str(repo_path),
        )
        if result.returncode != 0:
            logger.warning("Baseline eval failed (exit %d): %s",
                          result.returncode, result.stderr[-500:])
            return None

        # Parse the JSON output
        output = result.stdout.strip()
        if not output:
            logger.warning("Baseline eval produced no output")
            return None

        return json.loads(output)

    except subprocess.TimeoutExpired:
        logger.warning("Baseline eval timed out after 600s")
        return None
    except json.JSONDecodeError as e:
        logger.warning("Baseline eval output is not valid JSON: %s", e)
        return None
    except FileNotFoundError:
        logger.warning("uv not found. Install uv: https://docs.astral.sh/uv/")
        return None
