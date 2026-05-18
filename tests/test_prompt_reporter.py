"""Tests for repoaudit.reporters.prompt — render() and CLI --format prompt."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from repoaudit.reporters import prompt as prompt_module
from repoaudit.cli import main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fingerprint(
    repo_name: str = "my-service",
    language: str = "python",
    file_count: int = 42,
    has_git: bool = True,
    scores: dict | None = None,
    check_results: list | None = None,
) -> dict:
    if scores is None:
        scores = {
            "ai_readiness": 80.0,
            "security": 60.0,
            "devex": 40.0,
            "testing": 100.0,
            "overall": 70.0,
        }
    if check_results is None:
        check_results = []
    return {
        "repo_name": repo_name,
        "repo_path": f"/repos/{repo_name}",
        "language": {"language": language, "detected_by": ["requirements.txt"]},
        "file_count": file_count,
        "has_git": has_git,
        "score": scores,
        "check_results": check_results,
    }


def _failed_check(
    name: str,
    category: str = "security",
    severity: str = "required",
    message: str = "check failed",
    detail: str | None = None,
) -> dict:
    return {
        "name": name,
        "category": category,
        "passed": False,
        "severity": severity,
        "message": message,
        "detail": detail,
    }


def _passed_check(name: str, category: str = "testing") -> dict:
    return {
        "name": name,
        "category": category,
        "passed": True,
        "severity": "recommended",
        "message": "check passed",
        "detail": None,
    }


# ---------------------------------------------------------------------------
# render() unit tests
# ---------------------------------------------------------------------------

class TestPromptRender:
    def test_contains_repo_name(self) -> None:
        fp = _make_fingerprint(repo_name="vehicle-api")
        output = prompt_module.render(fp)
        assert "vehicle-api" in output

    def test_contains_all_failed_check_names(self) -> None:
        fp = _make_fingerprint(check_results=[
            _failed_check("no_claude_md", category="ai_readiness"),
            _failed_check("deps_not_pinned", category="security", severity="recommended"),
            _failed_check("no_tests", category="testing"),
        ])
        output = prompt_module.render(fp)
        assert "no_claude_md" in output
        assert "deps_not_pinned" in output
        assert "no_tests" in output

    def test_contains_score_table(self) -> None:
        fp = _make_fingerprint()
        output = prompt_module.render(fp)
        assert "## Scores" in output
        assert "AI Readiness" in output
        assert "Security" in output
        assert "Dev Experience" in output
        assert "Testing" in output

    def test_score_table_includes_status(self) -> None:
        fp = _make_fingerprint(scores={
            "ai_readiness": 90.0,
            "security": 60.0,
            "devex": 30.0,
            "testing": 100.0,
            "overall": 70.0,
        })
        output = prompt_module.render(fp)
        assert "OK" in output
        assert "WARN" in output
        assert "FAIL" in output

    def test_clean_repo_no_failed_checks(self) -> None:
        fp = _make_fingerprint(
            scores={
                "ai_readiness": 100.0,
                "security": 100.0,
                "devex": 100.0,
                "testing": 100.0,
                "overall": 100.0,
            },
            check_results=[_passed_check("all_good", "security")],
        )
        output = prompt_module.render(fp)
        # No "Failed Checks" sections
        assert "Failed Checks" not in output
        # Passed section present
        assert "Passed Checks" in output

    def test_prompt_ends_with_analysis_request(self) -> None:
        fp = _make_fingerprint()
        output = prompt_module.render(fp)
        assert "Please provide your analysis now." in output

    def test_prompt_includes_llm_instructions(self) -> None:
        fp = _make_fingerprint()
        output = prompt_module.render(fp)
        assert "expert code reviewer" in output
        assert "AI-friendly" in output

    def test_file_count_in_output(self) -> None:
        fp = _make_fingerprint(file_count=123)
        output = prompt_module.render(fp)
        assert "123" in output

    def test_has_git_shown(self) -> None:
        fp_git = _make_fingerprint(has_git=True)
        fp_no_git = _make_fingerprint(has_git=False)
        assert "Yes" in prompt_module.render(fp_git)
        assert "No" in prompt_module.render(fp_no_git)

    def test_failed_check_detail_included(self) -> None:
        fp = _make_fingerprint(check_results=[
            _failed_check(
                "no_readme",
                detail="Add a README.md with a Getting Started section.",
            )
        ])
        output = prompt_module.render(fp)
        assert "Add a README.md" in output

    def test_required_and_recommended_sections_separate(self) -> None:
        fp = _make_fingerprint(check_results=[
            _failed_check("req_fail", severity="required"),
            _failed_check("rec_fail", severity="recommended"),
        ])
        output = prompt_module.render(fp)
        assert "Failed Checks — Required" in output
        assert "Failed Checks — Recommended" in output

    def test_optional_failed_section(self) -> None:
        fp = _make_fingerprint(check_results=[
            _failed_check("opt_fail", severity="optional"),
        ])
        output = prompt_module.render(fp)
        assert "Not Implemented" in output


# ---------------------------------------------------------------------------
# CLI --format prompt tests (fingerprint command)
# ---------------------------------------------------------------------------

class TestFingerprintFormatPrompt:
    def test_format_prompt_outputs_prompt_text(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["fingerprint", str(tmp_path), "--format", "prompt"])
        assert result.exit_code == 0
        assert "expert code reviewer" in result.output

    def test_format_json_is_default(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["fingerprint", str(tmp_path)])
        assert result.exit_code == 0
        # Default must be JSON
        import json
        data = json.loads(result.output)
        assert "repo_name" in data

    def test_format_prompt_contains_repo_name(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["fingerprint", str(tmp_path), "--format", "prompt"])
        assert result.exit_code == 0
        assert tmp_path.name in result.output

    def test_format_prompt_output_to_file(self, tmp_path: Path) -> None:
        out_file = tmp_path / "prompt.txt"
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["fingerprint", str(tmp_path), "--format", "prompt", "--output", str(out_file)],
        )
        assert result.exit_code == 0
        assert out_file.exists()
        content = out_file.read_text(encoding="utf-8")
        assert "expert code reviewer" in content


# ---------------------------------------------------------------------------
# CLI --format prompt tests (analyze command)
# ---------------------------------------------------------------------------

class TestAnalyzeFormatPrompt:
    def test_analyze_format_prompt_appends_prompt_section(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["analyze", str(tmp_path), "--format", "prompt"])
        assert result.exit_code in (0, 1)  # may fail required checks → exit 1
        assert "expert code reviewer" in result.output
        # Static report part still present
        assert "repoaudit" in result.output

    def test_analyze_default_format_is_markdown(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["analyze", str(tmp_path)])
        assert result.exit_code in (0, 1)
        assert "expert code reviewer" not in result.output
        assert "## Findings" in result.output
