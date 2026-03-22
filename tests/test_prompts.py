"""Tests for the prompts module."""

from autoimprove.prompts import INSTRUCTIONS_MD


class TestInstructionsMd:
    def test_is_string(self):
        assert isinstance(INSTRUCTIONS_MD, str)

    def test_has_repo_name_placeholder(self):
        assert "{repo_name}" in INSTRUCTIONS_MD

    def test_has_experiment_duration_placeholder(self):
        assert "{experiment_duration}" in INSTRUCTIONS_MD

    def test_format_with_repo_name(self):
        result = INSTRUCTIONS_MD.format(repo_name="my-project", experiment_duration=300)
        assert "my-project" in result
        assert "{repo_name}" not in result

    def test_format_with_duration(self):
        result = INSTRUCTIONS_MD.format(repo_name="test", experiment_duration=600)
        assert "600" in result
        assert "{experiment_duration}" not in result

    def test_format_default_duration(self):
        result = INSTRUCTIONS_MD.format(repo_name="test", experiment_duration=300)
        assert "300" in result

    def test_has_phase_1(self):
        assert "Phase 1" in INSTRUCTIONS_MD
        assert "Understand the Repository" in INSTRUCTIONS_MD

    def test_has_phase_2(self):
        assert "Phase 2" in INSTRUCTIONS_MD
        assert "Evaluation System" in INSTRUCTIONS_MD

    def test_has_phase_3(self):
        assert "Phase 3" in INSTRUCTIONS_MD
        assert "program.md" in INSTRUCTIONS_MD

    def test_has_phase_4(self):
        assert "Phase 4" in INSTRUCTIONS_MD
        assert "config.yaml" in INSTRUCTIONS_MD

    def test_has_phase_5(self):
        assert "Phase 5" in INSTRUCTIONS_MD
        assert "Baseline" in INSTRUCTIONS_MD

    def test_has_never_stop(self):
        assert "NEVER STOP" in INSTRUCTIONS_MD

    def test_has_eval_harness_reference(self):
        assert "eval_harness.py" in INSTRUCTIONS_MD

    def test_has_evaluator_json_format(self):
        assert '"score"' in INSTRUCTIONS_MD
        assert '"name"' in INSTRUCTIONS_MD

    def test_has_checklist(self):
        assert "Checklist" in INSTRUCTIONS_MD

    def test_has_primary_metric_guidance(self):
        """Template must guide the agent to identify the project's primary metric."""
        assert "primary success metric" in INSTRUCTIONS_MD
        assert "Primary Evaluator" in INSTRUCTIONS_MD

    def test_has_primary_evaluator_examples(self):
        """Template must include examples of domain-specific evaluators."""
        assert "val_loss" in INSTRUCTIONS_MD
        assert "api_correctness" in INSTRUCTIONS_MD or "API server" in INSTRUCTIONS_MD
        assert "correctness" in INSTRUCTIONS_MD

    def test_has_time_budget_concept(self):
        """Template must reference experiment time budget."""
        assert "time budget" in INSTRUCTIONS_MD.lower()
        assert "experiment_duration_seconds" in INSTRUCTIONS_MD

    def test_no_unformatted_braces(self):
        """All braces except {repo_name} and {experiment_duration} should be escaped."""
        # Format with test values — if there are unescaped braces, this will fail
        try:
            INSTRUCTIONS_MD.format(repo_name="test", experiment_duration=300)
        except (KeyError, IndexError) as e:
            raise AssertionError(f"Unescaped brace in template: {e}")
