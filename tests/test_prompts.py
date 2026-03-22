"""Tests for the prompts module."""

from autoimprove.prompts import INSTRUCTIONS_MD


class TestInstructionsMd:
    def test_is_string(self):
        assert isinstance(INSTRUCTIONS_MD, str)

    def test_has_repo_name_placeholder(self):
        assert "{repo_name}" in INSTRUCTIONS_MD

    def test_format_with_repo_name(self):
        result = INSTRUCTIONS_MD.format(repo_name="my-project")
        assert "my-project" in result
        assert "{repo_name}" not in result

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

    def test_no_unformatted_braces(self):
        """All braces except {repo_name} should be escaped."""
        # Format with a test name — if there are unescaped braces, this will fail
        try:
            INSTRUCTIONS_MD.format(repo_name="test")
        except (KeyError, IndexError) as e:
            raise AssertionError(f"Unescaped brace in template: {e}")
