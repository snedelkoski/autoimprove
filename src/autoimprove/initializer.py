"""Initializer for autoimprove.

Generates the .autoimprove/ directory inside a target repo with all necessary
artifacts: config, program.md, eval harness, custom evaluators, and baselines.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from autoimprove.analyzer import analyze_repo, discover_evaluators
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
    FileClassification,
    LLMConfig,
    ProjectConfig,
    TechStack,
)
from autoimprove.llm import LLMClient
from autoimprove.prompts import (
    EVAL_HARNESS_TEMPLATE,
    GENERATE_PROGRAM_SYSTEM,
    GENERATE_PROGRAM_USER,
)

logger = logging.getLogger(__name__)


def initialize_repo(
    repo_path: Path,
    llm_config: LLMConfig | None = None,
    force: bool = False,
) -> ProjectConfig:
    """Initialize a repository for autoimprove.

    This is the main entry point for `autoimprove init`. It:
    1. Analyzes the repo (tech stack, file structure, etc.)
    2. Discovers custom evaluators via LLM
    3. Generates .autoimprove/ with all artifacts
    4. Runs baseline evaluation

    Args:
        repo_path: Path to the target repository root.
        llm_config: LLM configuration. Uses defaults if not provided.
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

    # Set up LLM client
    if llm_config is None:
        llm_config = LLMConfig()
    llm = LLMClient(llm_config)

    # --- Step 1: Analyze the repo ---
    print("Analyzing repository...")
    analysis = analyze_repo(repo_path, llm)

    tech_data = analysis.get("tech_stack", {})
    tech_stack = TechStack(**tech_data)

    file_class_data = analysis.get("file_classification", {})
    file_classification = FileClassification(**file_class_data)

    repo_summary = analysis.get("repo_summary", "")
    improvement_areas = analysis.get("improvement_areas", [])

    print(f"  Languages: {', '.join(tech_stack.languages)}")
    print(f"  Frameworks: {', '.join(tech_stack.frameworks)}")
    print(f"  Test command: {tech_stack.test_command or '(none detected)'}")
    print(f"  Mutable patterns: {', '.join(file_classification.mutable_patterns)}")
    print(f"  Protected patterns: {', '.join(file_classification.protected_patterns[:5])}...")

    # --- Step 2: Discover custom evaluators ---
    print("\nDiscovering evaluation metrics...")
    evaluator_defs = discover_evaluators(repo_path, analysis, llm)
    print(f"  Found {len(evaluator_defs)} custom evaluators:")
    for edef in evaluator_defs:
        print(f"    - {edef['name']}: {edef.get('description', '')}")

    # --- Step 3: Create .autoimprove/ directory ---
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
        tech_stack=tech_stack,
        file_classification=file_classification,
        evaluators=evaluator_configs,
        llm=llm_config,
    )
    config_path = ai_dir / CONFIG_FILE
    config.save(config_path)
    print(f"  Created {CONFIG_FILE}")

    # Write evaluator scripts
    evaluators_dir = ai_dir / EVALUATORS_DIR
    for edef in evaluator_defs:
        script_name = f"{edef['name']}.py"
        script_path = evaluators_dir / script_name
        script_content = edef.get("script_content", "")
        if script_content:
            script_path.write_text(script_content)
            script_path.chmod(0o755)
    print(f"  Created {len(evaluator_defs)} evaluator scripts")

    # Write eval harness
    harness_path = ai_dir / EVAL_HARNESS_FILE
    harness_path.write_text(EVAL_HARNESS_TEMPLATE)
    harness_path.chmod(0o755)
    print(f"  Created {EVAL_HARNESS_FILE}")

    # Generate program.md
    print("\nGenerating program.md...")
    program_md = _generate_program_md(
        llm=llm,
        repo_path=str(repo_path),
        repo_summary=repo_summary,
        tech_stack=tech_stack,
        file_classification=file_classification,
        evaluator_configs=evaluator_configs,
        improvement_areas=improvement_areas,
    )
    program_path = ai_dir / PROGRAM_FILE
    program_path.write_text(program_md)
    print(f"  Created {PROGRAM_FILE}")

    # Initialize results.tsv with header
    results_path = ai_dir / RESULTS_FILE
    results_path.write_text("experiment\tcomposite_score\tstatus\tdescription\n")
    print(f"  Created {RESULTS_FILE}")

    # --- Step 4: Run baseline evaluation ---
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
    print(f"Edit {PROGRAM_FILE} to customize agent behavior.")
    print(f"Run 'autoimprove run {repo_path}' to start autonomous improvement.")

    return config


def _create_directory_structure(ai_dir: Path) -> None:
    """Create the .autoimprove/ directory structure."""
    for subdir in [EVALUATORS_DIR, EXPERIMENTS_DIR, BASELINE_DIR]:
        (ai_dir / subdir).mkdir(parents=True, exist_ok=True)

    # Create __init__.py in evaluators so they can be a package if needed
    init_path = ai_dir / EVALUATORS_DIR / "__init__.py"
    if not init_path.exists():
        init_path.write_text("")


def _generate_program_md(
    llm: LLMClient,
    repo_path: str,
    repo_summary: str,
    tech_stack: TechStack,
    file_classification: FileClassification,
    evaluator_configs: list[EvaluatorConfig],
    improvement_areas: list[str],
) -> str:
    """Generate the program.md agent instruction file via LLM."""
    evaluator_descriptions = "\n".join(
        f"- {e.name} (weight={e.weight}): {e.description}"
        for e in evaluator_configs
    )

    user_prompt = GENERATE_PROGRAM_USER.format(
        repo_path=repo_path,
        repo_summary=repo_summary,
        languages=", ".join(tech_stack.languages),
        frameworks=", ".join(tech_stack.frameworks),
        build_system=tech_stack.build_system,
        package_manager=tech_stack.package_manager,
        test_framework=tech_stack.test_framework,
        test_command=tech_stack.test_command,
        build_command=tech_stack.build_command,
        mutable_patterns="\n".join(f"- {p}" for p in file_classification.mutable_patterns),
        protected_patterns="\n".join(f"- {p}" for p in file_classification.protected_patterns),
        evaluator_descriptions=evaluator_descriptions,
        improvement_areas="\n".join(f"- {a}" for a in improvement_areas),
    )

    return llm.analyze(
        GENERATE_PROGRAM_SYSTEM,
        user_prompt,
        temperature=0.5,
        max_tokens=4096,
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
