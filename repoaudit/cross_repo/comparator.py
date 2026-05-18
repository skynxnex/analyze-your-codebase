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

    return {
        "repos_analyzed": repos_analyzed,
        "common_failures": common_failures,
        "score_outliers": score_outliers,
        "language_mix": language_mix,
        "consistency": consistency,
        "best_repo": best_repo,
        "worst_repo": worst_repo,
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
