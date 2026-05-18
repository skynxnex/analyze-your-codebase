"""Tests for repoaudit.cross_repo.comparator."""

from __future__ import annotations

import pytest

from repoaudit.cross_repo.comparator import compare


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


@pytest.fixture
def three_fingerprints():
    """Three fingerprints where 2 fail the same check."""
    return [
        _make_fp(
            "service-a",
            check_results=[
                {
                    "name": "ci_runs_tests",
                    "category": "testing",
                    "passed": False,
                    "severity": "required",
                    "message": "CI does not run tests",
                },
                {
                    "name": "test_directory_exists",
                    "category": "testing",
                    "passed": True,
                    "severity": "required",
                    "message": "Test dir found",
                },
                {
                    "name": "claude_md_exists",
                    "category": "ai_readiness",
                    "passed": True,
                    "severity": "required",
                    "message": "CLAUDE.md found",
                },
                {
                    "name": "docker_compose_exists",
                    "category": "devex",
                    "passed": True,
                    "severity": "required",
                    "message": "docker-compose found",
                },
                {
                    "name": "deps_pinned",
                    "category": "security",
                    "passed": True,
                    "severity": "required",
                    "message": "deps pinned",
                },
                {
                    "name": "ci_config_exists",
                    "category": "testing",
                    "passed": True,
                    "severity": "required",
                    "message": "CI found",
                },
            ],
        ),
        _make_fp(
            "service-b",
            language="typescript_react",
            ai_readiness=60.0,
            security=100.0,
            devex=50.0,
            testing=40.0,
            check_results=[
                {
                    "name": "ci_runs_tests",
                    "category": "testing",
                    "passed": False,
                    "severity": "required",
                    "message": "CI does not run tests",
                },
                {
                    "name": "seed_script_exists",
                    "category": "devex",
                    "passed": False,
                    "severity": "recommended",
                    "message": "No seed script",
                },
                {
                    "name": "claude_md_exists",
                    "category": "ai_readiness",
                    "passed": True,
                    "severity": "required",
                    "message": "CLAUDE.md found",
                },
                {
                    "name": "docker_compose_exists",
                    "category": "devex",
                    "passed": True,
                    "severity": "required",
                    "message": "docker-compose found",
                },
                {
                    "name": "deps_pinned",
                    "category": "security",
                    "passed": False,
                    "severity": "required",
                    "message": "deps not pinned",
                },
                {
                    "name": "ci_config_exists",
                    "category": "testing",
                    "passed": False,
                    "severity": "required",
                    "message": "No CI found",
                },
            ],
        ),
        _make_fp(
            "service-c",
            check_results=[
                {
                    "name": "seed_script_exists",
                    "category": "devex",
                    "passed": False,
                    "severity": "recommended",
                    "message": "No seed script",
                },
                {
                    "name": "claude_md_exists",
                    "category": "ai_readiness",
                    "passed": True,
                    "severity": "required",
                    "message": "CLAUDE.md found",
                },
                {
                    "name": "docker_compose_exists",
                    "category": "devex",
                    "passed": True,
                    "severity": "required",
                    "message": "docker-compose found",
                },
                {
                    "name": "deps_pinned",
                    "category": "security",
                    "passed": True,
                    "severity": "required",
                    "message": "deps pinned",
                },
                {
                    "name": "ci_config_exists",
                    "category": "testing",
                    "passed": True,
                    "severity": "required",
                    "message": "CI found",
                },
                {
                    "name": "test_directory_exists",
                    "category": "testing",
                    "passed": True,
                    "severity": "required",
                    "message": "Test dir found",
                },
            ],
        ),
    ]


# ---------------------------------------------------------------------------
# common_failures
# ---------------------------------------------------------------------------


def test_common_failures_finds_check_failing_in_two_repos(three_fingerprints):
    result = compare(three_fingerprints)
    failure_names = [f["check"] for f in result["common_failures"]]
    assert "ci_runs_tests" in failure_names


def test_common_failures_sorted_by_failed_count_desc(three_fingerprints):
    result = compare(three_fingerprints)
    # seed_script_exists fails in 2, ci_runs_tests fails in 2 — both are equal at 2
    # Ensure all entries have failed_count >= 2
    for failure in result["common_failures"]:
        assert failure["failed_count"] >= 2


def test_common_failures_includes_repo_names(three_fingerprints):
    result = compare(three_fingerprints)
    ci_failure = next(
        (f for f in result["common_failures"] if f["check"] == "ci_runs_tests"), None
    )
    assert ci_failure is not None
    assert "service-a" in ci_failure["failed_in"]
    assert "service-b" in ci_failure["failed_in"]
    assert ci_failure["total_repos"] == 3


def test_common_failures_excludes_single_repo_failures(three_fingerprints):
    # test_directory_exists only fails in service-a (not present in service-c results as failed)
    result = compare(three_fingerprints)
    failure_names = [f["check"] for f in result["common_failures"]]
    # deps_pinned only fails in service-b — should not appear
    assert "deps_pinned" not in failure_names


# ---------------------------------------------------------------------------
# score_outliers
# ---------------------------------------------------------------------------


def test_score_outliers_triggers_when_below_threshold_and_avg_high(three_fingerprints):
    # service-b devex=50, service-a devex=80, service-c devex=80 → avg=70, delta=-20
    result = compare(three_fingerprints)
    outlier_repos = [(o["repo"], o["category"]) for o in result["score_outliers"]]
    assert ("service-b", "devex") in outlier_repos


def test_score_outliers_does_not_trigger_when_avg_below_60():
    # All repos have low testing scores — avg < 60, no outlier should be flagged
    fps = [
        _make_fp("svc-a", testing=30.0, ai_readiness=30.0, security=30.0, devex=30.0),
        _make_fp("svc-b", testing=20.0, ai_readiness=20.0, security=20.0, devex=20.0),
        _make_fp("svc-c", testing=10.0, ai_readiness=10.0, security=10.0, devex=10.0),
    ]
    result = compare(fps)
    assert result["score_outliers"] == []


def test_score_outliers_delta_must_exceed_20():
    # Scores are close — no outlier expected
    fps = [
        _make_fp("svc-a", testing=85.0),
        _make_fp("svc-b", testing=80.0),
        _make_fp("svc-c", testing=75.0),
    ]
    result = compare(fps)
    # avg ≈ 80, min is 75 — delta is only -5, below threshold
    testing_outliers = [o for o in result["score_outliers"] if o["category"] == "testing"]
    assert testing_outliers == []


# ---------------------------------------------------------------------------
# consistency
# ---------------------------------------------------------------------------


def test_consistency_all_have_claude_md_true(three_fingerprints):
    result = compare(three_fingerprints)
    assert result["consistency"]["all_have_claude_md"] is True


def test_consistency_all_deps_pinned_false(three_fingerprints):
    # service-b has deps_pinned=False
    result = compare(three_fingerprints)
    assert result["consistency"]["all_deps_pinned"] is False


def test_consistency_all_have_ci_false(three_fingerprints):
    # service-b has ci_config_exists=False
    result = compare(three_fingerprints)
    assert result["consistency"]["all_have_ci"] is False


def test_consistency_all_true_when_all_repos_pass():
    fps = [
        _make_fp(
            "svc-a",
            check_results=[
                {"name": "claude_md_exists", "category": "ai_readiness", "passed": True, "severity": "required", "message": ""},
                {"name": "docker_compose_exists", "category": "devex", "passed": True, "severity": "required", "message": ""},
                {"name": "test_directory_exists", "category": "testing", "passed": True, "severity": "required", "message": ""},
                {"name": "deps_pinned", "category": "security", "passed": True, "severity": "required", "message": ""},
                {"name": "ci_config_exists", "category": "testing", "passed": True, "severity": "required", "message": ""},
            ],
        ),
        _make_fp(
            "svc-b",
            check_results=[
                {"name": "claude_md_exists", "category": "ai_readiness", "passed": True, "severity": "required", "message": ""},
                {"name": "docker_compose_exists", "category": "devex", "passed": True, "severity": "required", "message": ""},
                {"name": "test_directory_exists", "category": "testing", "passed": True, "severity": "required", "message": ""},
                {"name": "deps_pinned", "category": "security", "passed": True, "severity": "required", "message": ""},
                {"name": "ci_config_exists", "category": "testing", "passed": True, "severity": "required", "message": ""},
            ],
        ),
    ]
    result = compare(fps)
    consistency = result["consistency"]
    assert consistency["all_have_claude_md"] is True
    assert consistency["all_have_docker_compose"] is True
    assert consistency["all_have_tests"] is True
    assert consistency["all_deps_pinned"] is True
    assert consistency["all_have_ci"] is True


# ---------------------------------------------------------------------------
# best_repo / worst_repo
# ---------------------------------------------------------------------------


def test_best_repo_is_highest_overall(three_fingerprints):
    result = compare(three_fingerprints)
    # service-a and service-c have overall=80, service-b has lower overall
    assert result["best_repo"] in ("service-a", "service-c")


def test_worst_repo_is_lowest_overall(three_fingerprints):
    result = compare(three_fingerprints)
    assert result["worst_repo"] == "service-b"


def test_best_worst_with_two_repos():
    fps = [
        _make_fp("high-scorer", ai_readiness=90.0, security=90.0, devex=90.0, testing=90.0),
        _make_fp("low-scorer", ai_readiness=40.0, security=40.0, devex=40.0, testing=40.0),
    ]
    result = compare(fps)
    assert result["best_repo"] == "high-scorer"
    assert result["worst_repo"] == "low-scorer"


def test_identical_scores_no_outliers():
    fps = [
        _make_fp("svc-a", ai_readiness=75.0, security=75.0, devex=75.0, testing=75.0),
        _make_fp("svc-b", ai_readiness=75.0, security=75.0, devex=75.0, testing=75.0),
        _make_fp("svc-c", ai_readiness=75.0, security=75.0, devex=75.0, testing=75.0),
    ]
    result = compare(fps)
    assert result["score_outliers"] == []


def test_repos_analyzed_count(three_fingerprints):
    result = compare(three_fingerprints)
    assert result["repos_analyzed"] == 3


def test_minimum_two_repos():
    fps = [
        _make_fp("svc-a"),
        _make_fp("svc-b", ai_readiness=50.0, security=50.0, devex=50.0, testing=50.0),
    ]
    result = compare(fps)
    assert result["repos_analyzed"] == 2
    assert result["best_repo"] == "svc-a"
    assert result["worst_repo"] == "svc-b"
