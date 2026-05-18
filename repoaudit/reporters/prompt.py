"""Prompt reporter.

Generates a self-contained text prompt from a repo fingerprint that can be
pasted into any LLM (Claude, ChatGPT, etc.) for qualitative analysis — no API
key required in the tool itself.
"""

from __future__ import annotations

_CATEGORY_LABELS: dict[str, str] = {
    "ai_readiness": "AI Readiness",
    "security": "Security",
    "devex": "Dev Experience",
    "testing": "Testing",
}

_SCORE_THRESHOLDS = {
    "pass": 80,
    "warn": 50,
}


def _status(score: float) -> str:
    if score >= _SCORE_THRESHOLDS["pass"]:
        return "OK"
    if score >= _SCORE_THRESHOLDS["warn"]:
        return "WARN"
    return "FAIL"


def render(fingerprint: dict) -> str:
    """Generate a paste-ready prompt for any LLM from a repo fingerprint.

    Args:
        fingerprint: The dict produced by ``repoaudit.fingerprint.build()``.

    Returns:
        A self-contained text prompt ready to paste into any LLM.
    """
    repo_name = fingerprint.get("repo_name", "unknown")
    language_info = fingerprint.get("language", {})
    lang_label = language_info.get("language", "unknown").replace("_", "/")
    scores = fingerprint.get("score", {})
    results = fingerprint.get("check_results", [])
    file_count = fingerprint.get("file_count", 0)
    has_git = fingerprint.get("has_git", False)
    overall = scores.get("overall", 0.0)

    failed = [r for r in results if not r["passed"]]
    passed = [r for r in results if r["passed"]]

    required_failed = [r for r in failed if r["severity"] == "required"]
    recommended_failed = [r for r in failed if r["severity"] == "recommended"]
    optional_failed = [r for r in failed if r["severity"] == "optional"]

    lines: list[str] = []

    # Instructions to the LLM
    lines.append(
        "You are an expert code reviewer. Below is a static analysis report "
        "for a software repository."
    )
    lines.append(
        "Please provide qualitative analysis covering:"
    )
    lines.append(
        "1. What the team is doing well (cite specific evidence from the data)"
    )
    lines.append(
        "2. Concerns that need attention (prioritized by impact)"
    )
    lines.append(
        "3. Whether this codebase is AI-friendly — could an AI confidently "
        "add a new feature?"
    )
    lines.append(
        "4. What single change would have the most impact on code quality?"
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    # Repository summary
    lines.append(f"## Repository: {repo_name}")
    lines.append(f"**Language**: {lang_label}")
    lines.append(f"**Scanned files**: {file_count}")
    lines.append(f"**Git repo**: {'Yes' if has_git else 'No'}")
    lines.append(f"**Overall score**: {overall:.0f}/100")
    lines.append("")

    # Score table
    lines.append("## Scores")
    lines.append("")
    lines.append("| Category | Score | Status |")
    lines.append("|---|---|---|")
    for cat, label in _CATEGORY_LABELS.items():
        score = scores.get(cat, 0.0)
        lines.append(f"| {label} | {score:.0f}% | {_status(score)} |")
    lines.append("")

    # Failed checks — most actionable data for the LLM
    if required_failed:
        lines.append("## Failed Checks — Required")
        lines.append("")
        for r in required_failed:
            lines.append(f"- **{r['name']}** [{r['category']}]: {r['message']}")
            if r.get("detail"):
                lines.append(f"  - {r['detail']}")
        lines.append("")

    if recommended_failed:
        lines.append("## Failed Checks — Recommended")
        lines.append("")
        for r in recommended_failed:
            lines.append(f"- **{r['name']}** [{r['category']}]: {r['message']}")
            if r.get("detail"):
                lines.append(f"  - {r['detail']}")
        lines.append("")

    if optional_failed:
        lines.append("## Not Implemented — Optional")
        lines.append("")
        for r in optional_failed:
            lines.append(f"- **{r['name']}** [{r['category']}]: {r['message']}")
            if r.get("detail"):
                lines.append(f"  - {r['detail']}")
        lines.append("")

    # Passed checks — summary grouped by category
    if passed:
        lines.append("## Passed Checks")
        lines.append("")
        by_category: dict[str, list[str]] = {}
        for r in passed:
            by_category.setdefault(r["category"], []).append(r["name"])
        for cat, names in sorted(by_category.items()):
            label = _CATEGORY_LABELS.get(cat, cat)
            lines.append(f"- **{label}**: {', '.join(names)}")
        lines.append("")
    else:
        lines.append("## Passed Checks")
        lines.append("")
        lines.append("No checks passed.")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("Please provide your analysis now.")

    return "\n".join(lines)
