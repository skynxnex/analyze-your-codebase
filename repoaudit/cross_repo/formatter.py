"""Per-repo inline detail formatter for multi-repo reports.

Renders a compact findings section for one fingerprint — failed checks only,
no passed list. Reuses the same check-result structure as markdown.py.
"""

from __future__ import annotations


def render_repo_detail(fingerprint: dict) -> str:
    """Return a compact Markdown string of failed checks for one repo.

    Only includes failed checks (required, recommended, optional). Does not
    include the passed-checks list to keep the multi-repo report compact.

    Args:
        fingerprint: A fingerprint dict as produced by ``fingerprint.build()``.

    Returns:
        Markdown-formatted string ready to embed in a multi-repo section.
    """
    results = fingerprint.get("check_results", [])

    required_failed = [r for r in results if not r["passed"] and r["severity"] == "required"]
    recommended_failed = [
        r for r in results if not r["passed"] and r["severity"] == "recommended"
    ]
    optional_failed = [r for r in results if not r["passed"] and r["severity"] == "optional"]

    lines: list[str] = []

    if not required_failed and not recommended_failed and not optional_failed:
        lines.append("All checks passed.")
        return "\n".join(lines)

    if required_failed:
        lines.append("**Required — FAILED**")
        lines.append("")
        for r in required_failed:
            lines.append(f"- **{r['name']}** [{r['category']}]: {r['message']}")
            if r.get("detail"):
                lines.append(f"  - {r['detail']}")
        lines.append("")

    if recommended_failed:
        lines.append("**Recommended — FAILED**")
        lines.append("")
        for r in recommended_failed:
            lines.append(f"- **{r['name']}** [{r['category']}]: {r['message']}")
            if r.get("detail"):
                lines.append(f"  - {r['detail']}")
        lines.append("")

    if optional_failed:
        lines.append("**Optional — not implemented**")
        lines.append("")
        for r in optional_failed:
            lines.append(f"- **{r['name']}** [{r['category']}]: {r['message']}")
            if r.get("detail"):
                lines.append(f"  - {r['detail']}")
        lines.append("")

    return "\n".join(lines)
