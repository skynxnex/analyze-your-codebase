"""Cross-repo comparator.

Finds common patterns (good and bad) across a list of repo fingerprints.
"""

from __future__ import annotations

_CONSISTENCY_CHECKS = {
    "all_have_claude_md": "claude_md_exists",
    "all_have_docker_compose": "docker_compose_exists",
    "all_have_tests": "test_directory_exists",
    "all_deps_pinned": "deps_pinned",
    "all_have_ci": "ci_config_exists",
}

_CATEGORIES = ("ai_readiness", "security", "devex", "testing")

_OUTLIER_THRESHOLD = 20.0
_OUTLIER_MIN_AVG = 60.0


def compare(fingerprints: list[dict]) -> dict:
    """Compare a list of repo fingerprints and return cross-repo findings.

    Args:
        fingerprints: List of fingerprint dicts as produced by
            ``repoaudit.fingerprint.build()``.

    Returns:
        A dict with keys: ``repos_analyzed``, ``common_failures``,
        ``score_outliers``, ``language_mix``, ``consistency``,
        ``best_repo``, ``worst_repo``.
    """
    repos_analyzed = len(fingerprints)

    common_failures = _find_common_failures(fingerprints)
    score_outliers = _find_score_outliers(fingerprints)
    language_mix = _build_language_mix(fingerprints)
    consistency = _build_consistency(fingerprints)
    best_repo, worst_repo = _find_best_worst(fingerprints)

    testing_patterns = _build_testing_patterns(fingerprints)
    security_patterns = _build_security_patterns(fingerprints)
    language_security_gaps = _build_language_security_gaps(fingerprints)

    return {
        "repos_analyzed": repos_analyzed,
        "common_failures": common_failures,
        "score_outliers": score_outliers,
        "language_mix": language_mix,
        "consistency": consistency,
        "best_repo": best_repo,
        "worst_repo": worst_repo,
        "testing_patterns": testing_patterns,
        "security_patterns": security_patterns,
        "language_security_gaps": language_security_gaps,
    }


def _find_common_failures(fingerprints: list[dict]) -> list[dict]:
    """Return checks that failed in 2+ repos, sorted by failed_count desc."""
    total_repos = len(fingerprints)

    # Map: check_name -> {category, failed_in: [repo_name, ...]}
    failure_map: dict[str, dict] = {}

    for fp in fingerprints:
        repo_name = fp.get("repo_name", "unknown")
        for result in fp.get("check_results", []):
            if not result.get("passed"):
                check_name = result.get("name", "")
                category = result.get("category", "")
                if check_name not in failure_map:
                    failure_map[check_name] = {
                        "category": category,
                        "failed_in": [],
                    }
                failure_map[check_name]["failed_in"].append(repo_name)

    common = []
    for check_name, info in failure_map.items():
        failed_count = len(info["failed_in"])
        if failed_count >= 2:
            common.append({
                "check": check_name,
                "category": info["category"],
                "failed_in": info["failed_in"],
                "failed_count": failed_count,
                "total_repos": total_repos,
            })

    common.sort(key=lambda x: x["failed_count"], reverse=True)
    return common


def _find_score_outliers(fingerprints: list[dict]) -> list[dict]:
    """Return repos significantly below platform average in any category."""
    if not fingerprints:
        return []

    # Compute per-category averages
    category_totals: dict[str, float] = {cat: 0.0 for cat in _CATEGORIES}
    category_counts: dict[str, int] = {cat: 0 for cat in _CATEGORIES}

    for fp in fingerprints:
        scores = fp.get("score", {})
        for cat in _CATEGORIES:
            if cat in scores:
                category_totals[cat] += scores[cat]
                category_counts[cat] += 1

    category_avgs: dict[str, float] = {}
    for cat in _CATEGORIES:
        count = category_counts[cat]
        category_avgs[cat] = category_totals[cat] / count if count else 0.0

    outliers = []
    for fp in fingerprints:
        repo_name = fp.get("repo_name", "unknown")
        scores = fp.get("score", {})
        for cat in _CATEGORIES:
            avg = category_avgs[cat]
            if avg < _OUTLIER_MIN_AVG:
                # No point flagging if everyone is bad
                continue
            repo_score = scores.get(cat, 0.0)
            delta = repo_score - avg
            if delta <= -_OUTLIER_THRESHOLD:
                outliers.append({
                    "repo": repo_name,
                    "category": cat,
                    "score": repo_score,
                    "avg_score": round(avg, 1),
                    "delta": round(delta, 1),
                })

    return outliers


def _build_language_mix(fingerprints: list[dict]) -> dict[str, list[str]]:
    """Return a mapping of language -> list of repo names."""
    mix: dict[str, list[str]] = {}
    for fp in fingerprints:
        lang = fp.get("language", {}).get("language", "unknown")
        repo_name = fp.get("repo_name", "unknown")
        mix.setdefault(lang, []).append(repo_name)
    return mix


def _build_consistency(fingerprints: list[dict]) -> dict[str, bool]:
    """Return consistency flags — True if ALL repos pass each check."""
    consistency: dict[str, bool] = {}

    for flag, check_name in _CONSISTENCY_CHECKS.items():
        all_pass = all(
            _repo_passes_check(fp, check_name)
            for fp in fingerprints
        )
        consistency[flag] = all_pass

    return consistency


def _repo_passes_check(fingerprint: dict, check_name: str) -> bool:
    """Return True if the fingerprint has a passing result for check_name."""
    for result in fingerprint.get("check_results", []):
        if result.get("name") == check_name:
            return bool(result.get("passed"))
    return False


def _get_repo_name(fp: dict) -> str:
    """Return the repo name from a fingerprint dict (supports both field names)."""
    return fp.get("repo_name") or fp.get("repo", "unknown")


def _get_check_results(fp: dict) -> list[dict]:
    """Return check results from a fingerprint dict (supports both field names)."""
    return fp.get("check_results") or fp.get("checks", [])


def _repos_failing_check(fingerprints: list[dict], check_name: str) -> list[str]:
    """Return list of repo names where the named check failed."""
    failing = []
    for fp in fingerprints:
        repo = _get_repo_name(fp)
        for result in _get_check_results(fp):
            if result.get("name") == check_name and not result.get("passed"):
                failing.append(repo)
                break
    return failing


def _build_testing_patterns(fingerprints: list[dict]) -> dict:
    """Aggregate testing-related check failures across repos."""
    total = len(fingerprints)

    missing_coverage = _repos_failing_check(fingerprints, "coverage_configured")
    missing_integration = _repos_failing_check(fingerprints, "integration_tests_exist")
    low_test_ratio = _repos_failing_check(fingerprints, "test_ratio")
    no_behavior_naming = _repos_failing_check(fingerprints, "tests_named_for_behavior")
    no_ci = _repos_failing_check(fingerprints, "ci_exists")

    parts = []
    if missing_coverage:
        parts.append(f"{len(missing_coverage)}/{total} repos missing coverage config")
    if missing_integration:
        parts.append(f"{len(missing_integration)}/{total} missing integration tests")
    if low_test_ratio:
        parts.append(f"{len(low_test_ratio)}/{total} with low test ratio")
    if no_behavior_naming:
        parts.append(f"{len(no_behavior_naming)}/{total} without behavior-named tests")
    if no_ci:
        parts.append(f"{len(no_ci)}/{total} missing CI")
    summary = ", ".join(parts) if parts else "No testing issues detected"

    return {
        "missing_coverage": missing_coverage,
        "missing_integration_tests": missing_integration,
        "low_test_ratio": low_test_ratio,
        "no_behavior_naming": no_behavior_naming,
        "no_ci": no_ci,
        "summary": summary,
    }


def _build_security_patterns(fingerprints: list[dict]) -> dict:
    """Aggregate security-related check failures across repos."""
    total = len(fingerprints)

    missing_auth = _repos_failing_check(fingerprints, "auth_middleware")
    wildcard_cors = _repos_failing_check(fingerprints, "cors_configured")
    no_dep_audit = _repos_failing_check(fingerprints, "dep_audit_in_ci")
    sensitive_logging = _repos_failing_check(fingerprints, "no_sensitive_logging")
    unauthenticated_outbound = _repos_failing_check(fingerprints, "service_auth")

    parts = []
    if missing_auth:
        parts.append(f"{len(missing_auth)}/{total} repos missing auth middleware")
    if wildcard_cors:
        parts.append(f"{len(wildcard_cors)}/{total} with CORS issues")
    if no_dep_audit:
        parts.append(f"{len(no_dep_audit)}/{total} missing dep audit in CI")
    if sensitive_logging:
        parts.append(f"{len(sensitive_logging)}/{total} with sensitive logging")
    if unauthenticated_outbound:
        parts.append(f"{len(unauthenticated_outbound)}/{total} missing service auth")
    summary = ", ".join(parts) if parts else "No security issues detected"

    return {
        "missing_auth": missing_auth,
        "wildcard_cors": wildcard_cors,
        "no_dep_audit": no_dep_audit,
        "sensitive_logging": sensitive_logging,
        "unauthenticated_outbound": unauthenticated_outbound,
        "summary": summary,
    }


def _build_language_security_gaps(fingerprints: list[dict]) -> list[dict]:
    """For each detected language, aggregate which security checks commonly fail.

    A check is considered a "common gap" if it fails in more than 50% of repos
    using that language.
    """
    _SECURITY_CHECKS = [
        "auth_middleware",
        "cors_configured",
        "dep_audit_in_ci",
        "no_sensitive_logging",
        "service_auth",
        "coverage_configured",
    ]

    # Group repos by language
    lang_repos: dict[str, list[dict]] = {}
    for fp in fingerprints:
        lang = fp.get("language", {}).get("language", "unknown")
        lang_repos.setdefault(lang, []).append(fp)

    result = []
    for lang, fps in lang_repos.items():
        repo_names = [_get_repo_name(fp) for fp in fps]
        total = len(fps)
        common_gaps = []
        for check_name in _SECURITY_CHECKS:
            failing = _repos_failing_check(fps, check_name)
            if len(failing) > total / 2:
                common_gaps.append(check_name)
        result.append({
            "language": lang,
            "repos": repo_names,
            "common_gaps": common_gaps,
        })

    return result


def _find_best_worst(fingerprints: list[dict]) -> tuple[str, str]:
    """Return (best_repo_name, worst_repo_name) by overall score."""
    if not fingerprints:
        return ("", "")

    sorted_fps = sorted(
        fingerprints,
        key=lambda fp: fp.get("score", {}).get("overall", 0.0),
    )
    worst = sorted_fps[0].get("repo_name", "unknown")
    best = sorted_fps[-1].get("repo_name", "unknown")
    return best, worst
