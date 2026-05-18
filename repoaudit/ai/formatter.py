"""Formats AI findings from ClaudeAnalyzer into a Markdown section."""

from __future__ import annotations

_MODEL_LABEL = "claude-haiku-4-5-20251001"


def format_ai_section(findings: dict) -> str:
    """Return a Markdown string for the AI analysis section.

    Args:
        findings: Dict returned by ``ClaudeAnalyzer.analyze()``.
            Expected keys: ``strengths``, ``concerns``, ``patterns``,
            ``ai_readiness_notes``, ``summary``.
            Gracefully handles missing keys and error keys.

    Returns:
        Markdown-formatted string ready to append to a report.
    """
    lines: list[str] = []

    lines.append("## AI Analysis")
    lines.append("")
    lines.append(f"> *Powered by Claude {_MODEL_LABEL} — qualitative analysis of sampled code*")
    lines.append("")

    error = findings.get("_error")
    if error:
        lines.append(f"> **Warning**: AI analysis could not complete — {error}")
        lines.append("")
        raw = findings.get("_raw")
        if raw:
            lines.append("<details><summary>Raw response</summary>")
            lines.append("")
            lines.append(raw)
            lines.append("")
            lines.append("</details>")
            lines.append("")
        return "\n".join(lines)

    strengths = findings.get("strengths") or []
    concerns = findings.get("concerns") or []
    patterns = findings.get("patterns") or []
    ai_readiness_notes = findings.get("ai_readiness_notes") or []
    summary = findings.get("summary") or ""

    lines.append("### What's working well")
    lines.append("")
    if strengths:
        for item in strengths:
            lines.append(f"- {item}")
    else:
        lines.append("- No specific strengths identified from the sampled files.")
    lines.append("")

    lines.append("### Concerns")
    lines.append("")
    if concerns:
        for item in concerns:
            lines.append(f"- {item}")
    else:
        lines.append("- No specific concerns identified from the sampled files.")
    lines.append("")

    lines.append("### AI-Readiness Notes")
    lines.append("")
    if ai_readiness_notes:
        for item in ai_readiness_notes:
            lines.append(f"- {item}")
    else:
        lines.append("- No specific AI-readiness observations from the sampled files.")
    lines.append("")

    lines.append("### Patterns observed")
    lines.append("")
    if patterns:
        for item in patterns:
            lines.append(f"- {item}")
    else:
        lines.append("- No cross-cutting patterns identified from the sampled files.")
    lines.append("")

    lines.append("### Summary")
    lines.append("")
    if summary:
        lines.append(summary)
    else:
        lines.append("No summary available.")
    lines.append("")

    return "\n".join(lines)
