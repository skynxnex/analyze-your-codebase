"""Tests for the HTML reporter (single-repo and multi-repo)."""

from __future__ import annotations

import pytest

from repoaudit.reporters import html as html_module


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_result(
    name: str,
    category: str,
    passed: bool,
    severity: str = "required",
    message: str = "ok",
    detail: str = "",
) -> dict:
    return {
        "name": name,
        "category": category,
        "passed": passed,
        "severity": severity,
        "message": message,
        "detail": detail,
    }


def _make_fingerprint(
    repo_name: str = "my-repo",
    language: str = "python",
    overall: float = 84.0,
    ai_readiness: float = 100.0,
    security: float = 70.0,
    devex: float = 88.0,
    testing: float = 80.0,
    file_count: int = 2422,
    has_git: bool = True,
    results: list[dict] | None = None,
) -> dict:
    if results is None:
        results = [
            _make_result("claude_md_exists", "ai_readiness", True, "required"),
            _make_result("no_hardcoded_secrets", "security", True, "required"),
            _make_result("deps_pinned", "security", False, "required", "5 unpinned entries"),
            _make_result(
                "seed_script_exists",
                "devex",
                False,
                "recommended",
                "No seed script found",
                "Add a db-seed script",
            ),
            _make_result("test_directory_exists", "testing", True, "required"),
        ]
    return {
        "repo_name": repo_name,
        "repo_path": f"/repos/{repo_name}",
        "language": {"language": language, "detected_by": ["requirements.txt"]},
        "score": {
            "overall": overall,
            "ai_readiness": ai_readiness,
            "security": security,
            "devex": devex,
            "testing": testing,
        },
        "check_results": results,
        "file_count": file_count,
        "has_git": has_git,
    }


def _make_comparison(fingerprints: list[dict]) -> dict:
    repo_names = [fp["repo_name"] for fp in fingerprints]
    return {
        "repos_analyzed": len(fingerprints),
        "language_mix": {"python": [repo_names[0]], "kotlin": repo_names[1:]},
        "best_repo": repo_names[0],
        "worst_repo": repo_names[-1],
        "consistency": {
            "all_have_claude_md": True,
            "all_have_docker_compose": False,
            "all_have_tests": True,
            "all_deps_pinned": False,
            "all_have_ci": True,
        },
        "common_failures": [
            {
                "check": "deps_pinned",
                "category": "security",
                "failed_in": repo_names,
                "failed_count": len(repo_names),
                "total_repos": len(repo_names),
            }
        ],
        "score_outliers": [],
    }


# ---------------------------------------------------------------------------
# Single-repo render() tests
# ---------------------------------------------------------------------------


def test_render_returns_valid_html():
    fp = _make_fingerprint()
    result = html_module.render(fp)
    assert result.startswith("<!DOCTYPE html>")
    assert "<html" in result
    assert "</html>" in result


def test_render_contains_repo_name():
    fp = _make_fingerprint(repo_name="cool-service")
    result = html_module.render(fp)
    assert "cool-service" in result


def test_render_contains_overall_score():
    fp = _make_fingerprint(overall=84.0)
    result = html_module.render(fp)
    assert "84" in result


def test_render_score_bar_width_reflects_score():
    fp = _make_fingerprint(overall=84.0)
    result = html_module.render(fp)
    assert "width: 84.0%" in result


def test_render_score_bar_width_for_low_score():
    fp = _make_fingerprint(overall=42.0)
    result = html_module.render(fp)
    assert "width: 42.0%" in result


def test_render_contains_failed_check_names():
    fp = _make_fingerprint()
    result = html_module.render(fp)
    assert "deps_pinned" in result
    assert "seed_script_exists" in result


def test_render_contains_passed_check_names():
    fp = _make_fingerprint()
    result = html_module.render(fp)
    assert "claude_md_exists" in result
    assert "no_hardcoded_secrets" in result
    assert "test_directory_exists" in result


def test_render_contains_category_scores():
    fp = _make_fingerprint(ai_readiness=100.0, security=70.0, devex=88.0, testing=80.0)
    result = html_module.render(fp)
    assert "100%" in result
    assert "70%" in result
    assert "88%" in result
    assert "80%" in result


def test_render_contains_language():
    fp = _make_fingerprint(language="python")
    result = html_module.render(fp)
    assert "python" in result


def test_render_git_badge_present():
    fp_git = _make_fingerprint(has_git=True)
    result_git = html_module.render(fp_git)
    assert "Git" in result_git

    fp_no_git = _make_fingerprint(has_git=False)
    result_no_git = html_module.render(fp_no_git)
    assert "No git" in result_no_git


def test_render_file_count_present():
    fp = _make_fingerprint(file_count=1234)
    result = html_module.render(fp)
    assert "1234" in result


def test_render_clean_repo_no_findings_section():
    """A repo with all checks passing should have no 'Required — FAILED' section."""
    results = [
        _make_result("claude_md_exists", "ai_readiness", True, "required"),
        _make_result("no_hardcoded_secrets", "security", True, "required"),
    ]
    fp = _make_fingerprint(results=results)
    result = html_module.render(fp)
    assert "Required" not in result or "FAILED" not in result


def test_render_finding_detail_appears():
    results = [
        _make_result(
            "deps_pinned",
            "security",
            False,
            "required",
            "5 unpinned entries",
            "Pin every package to exact version",
        )
    ]
    fp = _make_fingerprint(results=results)
    result = html_module.render(fp)
    assert "Pin every package to exact version" in result


def test_render_doctype_case():
    fp = _make_fingerprint()
    result = html_module.render(fp)
    assert "<!DOCTYPE html>" in result


# ---------------------------------------------------------------------------
# Multi-repo render_multi() tests
# ---------------------------------------------------------------------------


def _two_repos() -> tuple[list[dict], dict]:
    fp_a = _make_fingerprint(repo_name="service-alpha", language="python", overall=88.0)
    fp_b = _make_fingerprint(
        repo_name="service-beta",
        language="kotlin",
        overall=55.0,
        security=40.0,
    )
    fingerprints = [fp_a, fp_b]
    comparison = _make_comparison(fingerprints)
    return fingerprints, comparison


def test_render_multi_returns_valid_html():
    fingerprints, comparison = _two_repos()
    result = html_module.render_multi(fingerprints, comparison)
    assert result.startswith("<!DOCTYPE html>")
    assert "<html" in result
    assert "</html>" in result


def test_render_multi_contains_all_repo_names():
    fingerprints, comparison = _two_repos()
    result = html_module.render_multi(fingerprints, comparison)
    assert "service-alpha" in result
    assert "service-beta" in result


def test_render_multi_contains_platform_consistency_section():
    fingerprints, comparison = _two_repos()
    result = html_module.render_multi(fingerprints, comparison)
    assert "Platform Consistency" in result


def test_render_multi_contains_common_failures():
    fingerprints, comparison = _two_repos()
    result = html_module.render_multi(fingerprints, comparison)
    assert "Common Failures" in result
    assert "deps_pinned" in result


def test_render_multi_contains_overview_table():
    fingerprints, comparison = _two_repos()
    result = html_module.render_multi(fingerprints, comparison)
    assert "Overview" in result
    assert "<table" in result


def test_render_multi_per_repo_details_are_collapsible():
    fingerprints, comparison = _two_repos()
    result = html_module.render_multi(fingerprints, comparison)
    assert "<details" in result
    assert "<summary" in result


def test_render_multi_language_mix_in_header():
    fingerprints, comparison = _two_repos()
    result = html_module.render_multi(fingerprints, comparison)
    assert "python" in result
    assert "kotlin" in result


def test_render_multi_score_chips_present():
    fingerprints, comparison = _two_repos()
    result = html_module.render_multi(fingerprints, comparison)
    assert "chip-pass" in result or "chip-warn" in result or "chip-fail" in result


def test_render_multi_three_repos():
    fp_a = _make_fingerprint(repo_name="alpha", overall=90.0)
    fp_b = _make_fingerprint(repo_name="beta", overall=50.0, security=30.0)
    fp_c = _make_fingerprint(repo_name="gamma", overall=75.0)
    fingerprints = [fp_a, fp_b, fp_c]
    comparison = _make_comparison(fingerprints)
    result = html_module.render_multi(fingerprints, comparison)
    assert "alpha" in result
    assert "beta" in result
    assert "gamma" in result


def test_render_multi_no_common_failures():
    """render_multi should not crash if there are no common failures."""
    fingerprints, comparison = _two_repos()
    comparison["common_failures"] = []
    result = html_module.render_multi(fingerprints, comparison)
    assert result.startswith("<!DOCTYPE html>")


def test_render_multi_no_consistency():
    """render_multi should not crash if consistency dict is empty."""
    fingerprints, comparison = _two_repos()
    comparison["consistency"] = {}
    result = html_module.render_multi(fingerprints, comparison)
    assert result.startswith("<!DOCTYPE html>")
