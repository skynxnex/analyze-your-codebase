"""Tests for repoaudit.reporters.multi_markdown."""

from __future__ import annotations

import pytest

from repoaudit.reporters.multi_markdown import render, add_ai_section


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_fp(
    repo_name: str,
    language: str = "python_django",
    ai_readiness: float = 80.0,
    security: float = 80.0,
    devex: float = 80.0,
    testing: float = 80.0,
    check_results: list[dict] | None = None,
) -> dict:
    overall = round((ai_readiness + security + devex + testing) / 4, 1)
    return {
        "repo_name": repo_name,
        "language": {"language": language, "detected_by": []},
        "score": {
            "ai_readiness": ai_readiness,
            "security": security,
            "devex": devex,
            "testing": testing,
            "overall": overall,
        },
        "check_results": check_results or [],
        "file_count": 10,
        "has_git": True,
    }


def _make_comparison(
    fingerprints: list[dict],
    common_failures: list[dict] | None = None,
    score_outliers: list[dict] | None = None,
    consistency: dict | None = None,
    best_repo: str = "",
    worst_repo: str = "",
) -> dict:
    lang_mix: dict[str, list[str]] = {}
    for fp in fingerprints:
        lang = fp["language"]["language"]
        lang_mix.setdefault(lang, []).append(fp["repo_name"])
    return {
        "repos_analyzed": len(fingerprints),
        "common_failures": common_failures or [],
        "score_outliers": score_outliers or [],
        "language_mix": lang_mix,
        "consistency": consistency or {
            "all_have_claude_md": True,
            "all_have_docker_compose": True,
            "all_have_tests": True,
            "all_deps_pinned": False,
            "all_have_ci": False,
        },
        "best_repo": best_repo or (fingerprints[0]["repo_name"] if fingerprints else ""),
        "worst_repo": worst_repo or (fingerprints[-1]["repo_name"] if fingerprints else ""),
    }


@pytest.fixture
def two_fingerprints():
    return [
        _make_fp("service-a", testing=90.0),
        _make_fp("service-b", language="typescript_react", devex=50.0, testing=40.0),
    ]


@pytest.fixture
def two_comparison(two_fingerprints):
    return _make_comparison(
        two_fingerprints,
        common_failures=[
            {
                "check": "ci_runs_tests",
                "category": "testing",
                "failed_in": ["service-a", "service-b"],
                "failed_count": 2,
                "total_repos": 2,
            }
        ],
        score_outliers=[
            {
                "repo": "service-b",
                "category": "devex",
                "score": 50.0,
                "avg_score": 65.0,
                "delta": -15.0,
            }
        ],
        best_repo="service-a",
        worst_repo="service-b",
    )


# ---------------------------------------------------------------------------
# Overview table
# ---------------------------------------------------------------------------


def test_overview_table_contains_repo_names(two_fingerprints, two_comparison):
    report = render(two_fingerprints, two_comparison)
    assert "service-a" in report
    assert "service-b" in report


def test_overview_table_contains_language(two_fingerprints, two_comparison):
    report = render(two_fingerprints, two_comparison)
    assert "python_django" in report
    assert "typescript_react" in report


def test_overview_table_has_score_columns(two_fingerprints, two_comparison):
    report = render(two_fingerprints, two_comparison)
    assert "AI Ready" in report
    assert "Security" in report
    assert "DevEx" in report
    assert "Testing" in report
    assert "Overall" in report


def test_overview_best_worst_line(two_fingerprints, two_comparison):
    report = render(two_fingerprints, two_comparison)
    assert "service-a" in report
    assert "service-b" in report
    assert "Best:" in report
    assert "Needs most work:" in report


def test_header_shows_repos_analyzed(two_fingerprints, two_comparison):
    report = render(two_fingerprints, two_comparison)
    assert "Repos analyzed**: 2" in report


# ---------------------------------------------------------------------------
# Consistency table
# ---------------------------------------------------------------------------


def test_consistency_table_present(two_fingerprints, two_comparison):
    report = render(two_fingerprints, two_comparison)
    assert "Platform Consistency" in report


def test_consistency_table_shows_ok_for_true(two_fingerprints, two_comparison):
    report = render(two_fingerprints, two_comparison)
    # all_have_claude_md = True
    assert "All repos have CLAUDE.md" in report


def test_consistency_table_shows_fail_for_false(two_fingerprints, two_comparison):
    report = render(two_fingerprints, two_comparison)
    # all_deps_pinned = False → FAIL
    assert "All deps pinned" in report


# ---------------------------------------------------------------------------
# Common failures section
# ---------------------------------------------------------------------------


def test_common_failures_section_present(two_fingerprints, two_comparison):
    report = render(two_fingerprints, two_comparison)
    assert "Common Failures" in report


def test_common_failures_lists_check_name(two_fingerprints, two_comparison):
    report = render(two_fingerprints, two_comparison)
    assert "ci_runs_tests" in report


def test_common_failures_shows_repo_names(two_fingerprints, two_comparison):
    report = render(two_fingerprints, two_comparison)
    assert "service-a" in report
    assert "service-b" in report


def test_no_common_failures_section_when_empty(two_fingerprints):
    comparison = _make_comparison(two_fingerprints, common_failures=[])
    report = render(two_fingerprints, comparison)
    assert "Common Failures" not in report


# ---------------------------------------------------------------------------
# Per-repo details
# ---------------------------------------------------------------------------


def test_per_repo_details_section_present(two_fingerprints, two_comparison):
    report = render(two_fingerprints, two_comparison)
    assert "Per-Repo Details" in report


def test_per_repo_section_for_each_repo(two_fingerprints, two_comparison):
    fp_with_failures = _make_fp(
        "service-a",
        check_results=[
            {
                "name": "ci_runs_tests",
                "category": "testing",
                "passed": False,
                "severity": "required",
                "message": "CI does not run tests",
                "detail": "Add CI step.",
            },
        ],
    )
    fps = [fp_with_failures, _make_fp("service-b")]
    comparison = _make_comparison(fps, best_repo="service-b", worst_repo="service-a")
    report = render(fps, comparison)
    assert "### service-a" in report
    assert "### service-b" in report


def test_per_repo_detail_shows_failed_checks(two_fingerprints, two_comparison):
    fp_with_failures = _make_fp(
        "service-a",
        check_results=[
            {
                "name": "ci_runs_tests",
                "category": "testing",
                "passed": False,
                "severity": "required",
                "message": "CI does not run tests",
                "detail": None,
            },
        ],
    )
    fps = [fp_with_failures, _make_fp("service-b")]
    comparison = _make_comparison(fps, best_repo="service-b", worst_repo="service-a")
    report = render(fps, comparison)
    assert "ci_runs_tests" in report
    assert "Required — FAILED" in report


# ---------------------------------------------------------------------------
# Minimum 2 repos
# ---------------------------------------------------------------------------


def test_render_works_with_two_repos(two_fingerprints, two_comparison):
    report = render(two_fingerprints, two_comparison)
    assert "multi-repo analysis" in report
    assert "service-a" in report
    assert "service-b" in report


# ---------------------------------------------------------------------------
# AI section
# ---------------------------------------------------------------------------


def test_add_ai_section_appends_to_report(two_fingerprints, two_comparison):
    report = render(two_fingerprints, two_comparison)
    ai_findings = {
        "strengths": ["Consistent use of Docker"],
        "concerns": ["Missing CI in some repos"],
        "patterns": ["All repos follow Django conventions"],
        "ai_readiness_notes": ["Good CLAUDE.md coverage"],
        "summary": "Solid platform with some CI gaps.",
    }
    full_report = add_ai_section(report, ai_findings)
    assert "AI Analysis (cross-repo)" in full_report
    assert "Consistent use of Docker" in full_report
    assert "Solid platform with some CI gaps." in full_report


def test_add_ai_section_error_shows_warning(two_fingerprints, two_comparison):
    report = render(two_fingerprints, two_comparison)
    ai_findings = {
        "strengths": [],
        "concerns": [],
        "patterns": [],
        "ai_readiness_notes": [],
        "summary": "",
        "_error": "API call failed: timeout",
    }
    full_report = add_ai_section(report, ai_findings)
    assert "Warning" in full_report
    assert "timeout" in full_report
