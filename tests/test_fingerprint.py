"""Tests for repoaudit.fingerprint — build() and scoring logic."""

from __future__ import annotations

from pathlib import Path

import pytest

from repoaudit.checks.base import CheckResult
from repoaudit import fingerprint as fp_module


_LANG = {"language": "python", "detected_by": ["requirements.txt"]}


def _make_result(
    name: str,
    category: str,
    passed: bool,
    severity: str = "required",
) -> CheckResult:
    return CheckResult(
        name=name,
        category=category,
        passed=passed,
        severity=severity,
        message=f"{name} {'passed' if passed else 'failed'}",
    )


# ---------------------------------------------------------------------------
# Score calculation
# ---------------------------------------------------------------------------

class TestScoreCalculation:
    def test_all_required_passed_gives_100_for_category(self, tmp_path: Path) -> None:
        results = [
            _make_result("check_a", "security", True, "required"),
            _make_result("check_b", "security", True, "required"),
        ]
        fp = fp_module.build(tmp_path, _LANG, results)
        assert fp["score"]["security"] == 100.0

    def test_all_required_failed_gives_0_for_category(self, tmp_path: Path) -> None:
        results = [
            _make_result("check_a", "security", False, "required"),
            _make_result("check_b", "security", False, "required"),
        ]
        fp = fp_module.build(tmp_path, _LANG, results)
        assert fp["score"]["security"] == 0.0

    def test_mixed_required_recommended_scoring(self, tmp_path: Path) -> None:
        # required weight=3, recommended weight=1
        # 1 required passed (3) + 1 recommended failed (0) / total (3+1) = 75%
        results = [
            _make_result("req_pass", "devex", True, "required"),
            _make_result("rec_fail", "devex", False, "recommended"),
        ]
        fp = fp_module.build(tmp_path, _LANG, results)
        assert fp["score"]["devex"] == 75.0

    def test_optional_checks_do_not_affect_score(self, tmp_path: Path) -> None:
        results = [
            _make_result("req_pass", "testing", True, "required"),
            _make_result("opt_fail", "testing", False, "optional"),  # weight=0
        ]
        fp = fp_module.build(tmp_path, _LANG, results)
        assert fp["score"]["testing"] == 100.0

    def test_empty_category_scores_100(self, tmp_path: Path) -> None:
        # No checks for ai_readiness — should be 100 (not applicable).
        results = [
            _make_result("check_a", "security", True, "required"),
        ]
        fp = fp_module.build(tmp_path, _LANG, results)
        assert fp["score"]["ai_readiness"] == 100.0

    def test_overall_is_average_of_four_categories(self, tmp_path: Path) -> None:
        # All categories empty → all 100 → overall 100
        fp = fp_module.build(tmp_path, _LANG, [])
        assert fp["score"]["overall"] == 100.0

    def test_overall_reflects_partial_scores(self, tmp_path: Path) -> None:
        # security=0, rest empty (100 each) → (0+100+100+100)/4 = 75
        results = [
            _make_result("sec_fail", "security", False, "required"),
        ]
        fp = fp_module.build(tmp_path, _LANG, results)
        assert fp["score"]["overall"] == 75.0


# ---------------------------------------------------------------------------
# Fingerprint structure
# ---------------------------------------------------------------------------

class TestFingerprintStructure:
    def test_contains_required_top_level_keys(self, tmp_path: Path) -> None:
        fp = fp_module.build(tmp_path, _LANG, [])
        expected_keys = {
            "repo_path", "repo_name", "language",
            "check_results", "score", "file_count", "has_git",
        }
        assert expected_keys.issubset(fp.keys())

    def test_repo_name_is_directory_basename(self, tmp_path: Path) -> None:
        fp = fp_module.build(tmp_path, _LANG, [])
        assert fp["repo_name"] == tmp_path.resolve().name

    def test_has_git_false_when_no_git_dir(self, tmp_path: Path) -> None:
        fp = fp_module.build(tmp_path, _LANG, [])
        assert fp["has_git"] is False

    def test_has_git_true_when_git_dir_exists(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        fp = fp_module.build(tmp_path, _LANG, [])
        assert fp["has_git"] is True

    def test_check_results_serialised_as_dicts(self, tmp_path: Path) -> None:
        results = [_make_result("foo", "security", True)]
        fp = fp_module.build(tmp_path, _LANG, results)
        assert isinstance(fp["check_results"], list)
        first = fp["check_results"][0]
        assert isinstance(first, dict)
        assert first["name"] == "foo"
        assert first["passed"] is True

    def test_file_count_counts_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("x")
        (tmp_path / "b.py").write_text("x")
        fp = fp_module.build(tmp_path, _LANG, [])
        assert fp["file_count"] >= 2

    def test_language_preserved_in_fingerprint(self, tmp_path: Path) -> None:
        fp = fp_module.build(tmp_path, _LANG, [])
        assert fp["language"] == _LANG

    def test_score_dict_has_all_four_categories_plus_overall(self, tmp_path: Path) -> None:
        fp = fp_module.build(tmp_path, _LANG, [])
        assert set(fp["score"].keys()) == {
            "ai_readiness", "security", "devex", "testing", "overall"
        }


# ---------------------------------------------------------------------------
# End-to-end: run real checks against a mock repo
# ---------------------------------------------------------------------------

class TestEndToEnd:
    def test_well_configured_repo_scores_high(self, tmp_path: Path) -> None:
        """A repo with all key files should score >= 70 overall."""
        from repoaudit.checks import ALL_CHECKS
        from repoaudit.detectors.language import detect

        # Set up a reasonably complete Python repo.
        (tmp_path / "CLAUDE.md").write_text("# CLAUDE\n" * 10)
        readme = "\n".join([f"## Section {i}\n\nContent here." for i in range(12)])
        (tmp_path / "README.md").write_text(
            "# My Service\n\n## Getting Started\n\nRun docker compose up.\n\n"
            + readme
        )
        (tmp_path / "requirements.txt").write_text("click==8.1.8\npyyaml==6.0.2\n")
        (tmp_path / "Dockerfile").write_text("FROM python:3.11-slim\nWORKDIR /app\n")
        (tmp_path / "docker-compose.yml").write_text(
            "services:\n  app:\n    build: .\n"
        )
        (tmp_path / "pyproject.toml").write_text(
            "[tool.pytest.ini_options]\ntestpaths = [\"tests\"]\n"
        )
        (tmp_path / ".gitignore").write_text(".env\n*.pyc\n")
        (tmp_path / ".env.example").write_text("DATABASE_URL=\n")
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_app.py").write_text(
            "def test_should_return_ok():\n    assert True\n"
        )

        language = detect(tmp_path)
        results = []
        for check_cls in ALL_CHECKS:
            results.extend(check_cls().run(tmp_path, language))

        fp = fp_module.build(tmp_path, language, results)
        assert fp["score"]["overall"] >= 70.0

    def test_empty_repo_scores_low(self, tmp_path: Path) -> None:
        """An empty directory should score below 40 overall."""
        from repoaudit.checks import ALL_CHECKS
        from repoaudit.detectors.language import detect

        language = detect(tmp_path)
        results = []
        for check_cls in ALL_CHECKS:
            results.extend(check_cls().run(tmp_path, language))

        fp = fp_module.build(tmp_path, language, results)
        assert fp["score"]["overall"] < 40.0
