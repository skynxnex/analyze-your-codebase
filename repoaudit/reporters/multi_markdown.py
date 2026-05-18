"""Multi-repo Markdown reporter.

Renders a combined human-readable Markdown report from a list of repo
fingerprints and the cross-repo comparison dict.
"""

from __future__ import annotations

from repoaudit.cross_repo.formatter import render_repo_detail

_CATEGORIES = ("ai_readiness", "security", "devex", "testing")

_CATEGORY_HEADERS: dict[str, str] = {
    "ai_readiness": "AI Ready",
    "security": "Security",
    "devex": "DevEx",
    "testing": "Testing",
}

_CONSISTENCY_LABELS: dict[str, str] = {
    "all_have_claude_md": "All repos have CLAUDE.md",
    "all_have_docker_compose": "All repos have docker-compose",
    "all_have_tests": "All repos have tests",
    "all_deps_pinned": "All deps pinned",
    "all_have_ci": "All have CI",
}


def _score_icon(score: float) -> str:
    """Return a status icon based on score thresholds."""
    if score >= 80:
        return "OK"
    if score >= 60:
        return "WARN"
    return "FAIL"


def render(fingerprints: list[dict], comparison: dict) -> str:
    """Return a combined Markdown report for multiple repos.

    Args:
        fingerprints: List of fingerprint dicts, one per repo.
        comparison: The dict returned by ``comparator.compare()``.

    Returns:
        Markdown-formatted string.
    """
    repos_analyzed = comparison.get("repos_analyzed", len(fingerprints))
    lang_mix = comparison.get("language_mix", {})
    best_repo = comparison.get("best_repo", "")
    worst_repo = comparison.get("worst_repo", "")

    lines: list[str] = []

    # Header
    lines.append("# repoaudit — multi-repo analysis")
    lines.append("")
    lines.append(f"**Repos analyzed**: {repos_analyzed}  ")

    if lang_mix:
        lang_summary = ", ".join(
            f"{lang} ({len(repos)})" for lang, repos in lang_mix.items()
        )
        lines.append(f"**Languages**: {lang_summary}  ")
    lines.append("")

    # Overview table
    lines.append("## Overview")
    lines.append("")
    cat_headers = " | ".join(_CATEGORY_HEADERS[cat] for cat in _CATEGORIES)
    lines.append(f"| Repo | Language | {cat_headers} | Overall |")
    lines.append("|" + "---|" * (len(_CATEGORIES) + 3))

    for fp in fingerprints:
        repo_name = fp.get("repo_name", "unknown")
        lang = fp.get("language", {}).get("language", "unknown")
        scores = fp.get("score", {})
        overall = scores.get("overall", 0.0)

        cat_cells = []
        for cat in _CATEGORIES:
            score = scores.get(cat, 0.0)
            icon = _score_icon(score)
            cat_cells.append(f"{score:.0f}% {icon}")

        cat_str = " | ".join(cat_cells)
        lines.append(
            f"| {repo_name} | {lang} | {cat_str} | **{overall:.0f}** |"
        )

    lines.append("")

    if best_repo or worst_repo:
        parts = []
        if best_repo:
            best_fp = next((fp for fp in fingerprints if fp.get("repo_name") == best_repo), None)
            best_score = best_fp["score"]["overall"] if best_fp else 0.0
            parts.append(f"Best: **{best_repo}** ({best_score:.0f}/100)")
        if worst_repo and worst_repo != best_repo:
            worst_fp = next(
                (fp for fp in fingerprints if fp.get("repo_name") == worst_repo), None
            )
            worst_score = worst_fp["score"]["overall"] if worst_fp else 0.0
            parts.append(f"Needs most work: **{worst_repo}** ({worst_score:.0f}/100)")
        if parts:
            lines.append(" — ".join(parts))
            lines.append("")

    # Platform Consistency
    consistency = comparison.get("consistency", {})
    if consistency:
        lines.append("## Platform Consistency")
        lines.append("")
        lines.append("| Check | Status |")
        lines.append("|---|---|")
        for flag, value in consistency.items():
            label = _CONSISTENCY_LABELS.get(flag, flag.replace("_", " ").title())
            icon = "OK" if value else "FAIL"
            lines.append(f"| {label} | {icon} |")
        lines.append("")

    # Common Failures
    common_failures = comparison.get("common_failures", [])
    if common_failures:
        lines.append("## Common Failures (across repos)")
        lines.append("")
        lines.append(
            "These checks failed in multiple repos — highest priority to fix platform-wide:"
        )
        lines.append("")
        for failure in common_failures:
            check = failure.get("check", "")
            category = failure.get("category", "")
            failed_in = ", ".join(failure.get("failed_in", []))
            failed_count = failure.get("failed_count", 0)
            total = failure.get("total_repos", 0)
            lines.append(
                f"- **{check}** [{category}] — failed in {failed_count}/{total} repos: {failed_in}"
            )
        lines.append("")

    # Score Outliers
    score_outliers = comparison.get("score_outliers", [])
    if score_outliers:
        lines.append("## Score Outliers")
        lines.append("")
        lines.append("Repos significantly below platform average in a category:")
        lines.append("")
        for outlier in score_outliers:
            repo = outlier.get("repo", "")
            category = outlier.get("category", "")
            score = outlier.get("score", 0.0)
            avg = outlier.get("avg_score", 0.0)
            delta = outlier.get("delta", 0.0)
            lines.append(
                f"- **{repo}** / {category}: {score:.0f}% "
                f"(platform avg: {avg:.0f}%) — {abs(delta):.0f} points below average"
            )
        lines.append("")

    # Per-Repo Details
    lines.append("## Per-Repo Details")
    lines.append("")

    for fp in fingerprints:
        repo_name = fp.get("repo_name", "unknown")
        overall = fp.get("score", {}).get("overall", 0.0)
        lines.append(f"### {repo_name} ({overall:.0f}/100)")
        lines.append("")
        detail = render_repo_detail(fp)
        lines.append(detail)
        if not detail.endswith("\n"):
            lines.append("")

    return "\n".join(lines)


def add_ai_section(report: str, ai_findings: dict) -> str:
    """Append an AI cross-repo analysis section to an existing report.

    Args:
        report: The existing Markdown report produced by :func:`render`.
        ai_findings: The dict returned by ``CrossRepoAnalyzer.analyze()``.

    Returns:
        New string with the AI section appended.
    """
    from repoaudit.ai.formatter import format_ai_section  # lazy import

    ai_section = format_ai_section(ai_findings)
    # Replace the heading to make it clear this is cross-repo analysis
    ai_section = ai_section.replace(
        "## AI Analysis",
        "## AI Analysis (cross-repo)",
        1,
    )
    return report + "\n---\n\n" + ai_section
