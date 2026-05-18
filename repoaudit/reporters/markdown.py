"""Markdown reporter.

Renders a human-readable Markdown report from a repo fingerprint dict.
"""

from __future__ import annotations

_SCORE_THRESHOLDS = {
    "pass": 80,
    "warn": 50,
}

_CATEGORY_LABELS: dict[str, str] = {
    "ai_readiness": "AI Readiness",
    "security": "Security",
    "devex": "Dev Experience",
    "testing": "Testing",
}


def _status_icon(score: float) -> str:
    if score >= _SCORE_THRESHOLDS["pass"]:
        return "OK"
    if score >= _SCORE_THRESHOLDS["warn"]:
        return "WARN"
    return "FAIL"


def render(fingerprint: dict) -> str:
    """Return a Markdown string for the given *fingerprint*."""
    repo_name = fingerprint.get("repo_name", "unknown")
    language_info = fingerprint.get("language", {})
    lang_label = language_info.get("language", "unknown").replace("_", "/")
    scores = fingerprint.get("score", {})
    results = fingerprint.get("check_results", [])
    overall = scores.get("overall", 0.0)
    file_count = fingerprint.get("file_count", 0)
    has_git = fingerprint.get("has_git", False)

    lines: list[str] = []

    # Header
    lines.append(f"# repoaudit — {repo_name}")
    lines.append("")
    lines.append(f"**Language**: {lang_label}  ")
    lines.append(f"**Overall score**: {overall:.0f}/100  ")
    lines.append(f"**Files scanned**: {file_count}  ")
    lines.append(f"**Git repo**: {'Yes' if has_git else 'No'}  ")
    lines.append("")

    # Score table
    lines.append("## Scores")
    lines.append("")
    lines.append("| Category | Score | Status |")
    lines.append("|---|---|---|")
    for cat, label in _CATEGORY_LABELS.items():
        score = scores.get(cat, 0.0)
        icon = _status_icon(score)
        lines.append(f"| {label} | {score:.0f}% | {icon} |")
    lines.append("")

    # Findings
    lines.append("## Findings")
    lines.append("")

    required_failed = [r for r in results if not r["passed"] and r["severity"] == "required"]
    recommended_failed = [r for r in results if not r["passed"] and r["severity"] == "recommended"]
    optional_failed = [r for r in results if not r["passed"] and r["severity"] == "optional"]
    passed_all = [r for r in results if r["passed"]]

    if required_failed:
        lines.append("### Required — FAILED")
        lines.append("")
        for r in required_failed:
            lines.append(f"- **{r['name']}** [{r['category']}]: {r['message']}")
            if r.get("detail"):
                lines.append(f"  - {r['detail']}")
        lines.append("")

    if recommended_failed:
        lines.append("### Recommended — FAILED")
        lines.append("")
        for r in recommended_failed:
            lines.append(f"- **{r['name']}** [{r['category']}]: {r['message']}")
            if r.get("detail"):
                lines.append(f"  - {r['detail']}")
        lines.append("")

    if optional_failed:
        lines.append("### Optional — not implemented")
        lines.append("")
        for r in optional_failed:
            lines.append(f"- **{r['name']}** [{r['category']}]: {r['message']}")
            if r.get("detail"):
                lines.append(f"  - {r['detail']}")
        lines.append("")

    if passed_all:
        lines.append("### Passed")
        lines.append("")
        # Group by category for readability.
        by_category: dict[str, list[str]] = {}
        for r in passed_all:
            by_category.setdefault(r["category"], []).append(r["name"])
        for cat, names in sorted(by_category.items()):
            label = _CATEGORY_LABELS.get(cat, cat)
            lines.append(f"- **{label}**: {', '.join(names)}")
        lines.append("")

    return "\n".join(lines)


def add_ai_section(report: str, ai_findings: dict) -> str:
    """Append an AI analysis section to an existing Markdown *report* string.

    Args:
        report: The existing Markdown report produced by :func:`render`.
        ai_findings: The dict returned by ``ClaudeAnalyzer.analyze()``.

    Returns:
        New string with the AI section appended.
    """
    from repoaudit.ai.formatter import format_ai_section  # lazy import — only when --ai is used

    return report + "\n" + format_ai_section(ai_findings)
