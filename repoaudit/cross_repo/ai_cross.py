"""Cross-repo AI analysis using Claude.

Sends a compact summary of cross-repo comparison data to Claude and returns
structured findings about platform-wide patterns.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM_PROMPT = """\
You are an expert platform engineer performing qualitative analysis across
multiple codebases that belong to the same platform or organisation.

You will receive a cross-repo comparison summary including scores per repo,
common failures across repos, and consistency flags.

Your job is to identify:
- What patterns are consistent (good or bad) across all repos?
- Which repos deviate significantly and what might explain the deviation?
- What should be standardised across the platform?
- Are there signs this is a single coherent platform or a collection of
  unrelated services?

Guidelines:
- Be specific. Reference repo names and check names from the data provided.
- Be honest about both strengths and weaknesses.
- Focus only on what you can see in the summary — do not invent issues.
- Think like a platform team doing a quarterly health review.

Return ONLY valid JSON — no markdown fences, no explanation, nothing outside
the JSON object.

The JSON must have exactly these keys:
{
  "strengths": ["list of specific platform-wide strengths"],
  "concerns": ["list of specific platform-wide concerns"],
  "patterns": ["cross-cutting observations about consistency or divergence"],
  "ai_readiness_notes": ["observations about platform-wide AI-friendliness"],
  "summary": "2-3 sentence overall assessment of the platform health"
}
"""

_EMPTY_FINDINGS: dict = {
    "strengths": [],
    "concerns": [],
    "patterns": [],
    "ai_readiness_notes": [],
    "summary": "",
}

_TOP_FAILURES_LIMIT = 5
_CATEGORIES = ("ai_readiness", "security", "devex", "testing")


def _strip_fences(text: str) -> str:
    """Strip markdown code fences from a string if present."""
    clean = text.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[-1]
        if clean.endswith("```"):
            clean = clean.rsplit("```", 1)[0]
        clean = clean.strip()
    return clean


def _build_user_message(comparison: dict, fingerprints: list[dict]) -> str:
    """Build the user-turn message from comparison data and fingerprint scores."""
    parts: list[str] = []

    parts.append("## Cross-Repo Comparison Summary")
    parts.append("")
    parts.append(f"Repos analyzed: {comparison.get('repos_analyzed', 0)}")

    lang_mix = comparison.get("language_mix", {})
    if lang_mix:
        lang_summary = ", ".join(
            f"{lang} ({len(repos)})" for lang, repos in lang_mix.items()
        )
        parts.append(f"Languages: {lang_summary}")

    best = comparison.get("best_repo", "")
    worst = comparison.get("worst_repo", "")
    if best:
        parts.append(f"Best overall: {best}")
    if worst:
        parts.append(f"Needs most work: {worst}")

    # Score table per repo
    parts.append("")
    parts.append("## Per-Repo Score Table")
    parts.append("")
    header_cats = " | ".join(cat.replace("_", " ").title() for cat in _CATEGORIES)
    parts.append(f"| Repo | Language | {header_cats} | Overall |")
    parts.append("|" + "---|" * (len(_CATEGORIES) + 3))

    for fp in fingerprints:
        repo_name = fp.get("repo_name", "unknown")
        lang = fp.get("language", {}).get("language", "unknown")
        scores = fp.get("score", {})
        cat_scores = " | ".join(
            f"{scores.get(cat, 0.0):.0f}%" for cat in _CATEGORIES
        )
        overall = scores.get("overall", 0.0)
        parts.append(f"| {repo_name} | {lang} | {cat_scores} | {overall:.0f} |")

    # Common failures (top N)
    common_failures = comparison.get("common_failures", [])
    if common_failures:
        parts.append("")
        parts.append("## Top Common Failures")
        parts.append("")
        for failure in common_failures[:_TOP_FAILURES_LIMIT]:
            check = failure.get("check", "")
            category = failure.get("category", "")
            failed_in = ", ".join(failure.get("failed_in", []))
            failed_count = failure.get("failed_count", 0)
            total = failure.get("total_repos", 0)
            parts.append(
                f"- **{check}** [{category}] — failed in {failed_count}/{total} repos: {failed_in}"
            )

    # Score outliers
    outliers = comparison.get("score_outliers", [])
    if outliers:
        parts.append("")
        parts.append("## Score Outliers")
        parts.append("")
        for outlier in outliers:
            repo = outlier.get("repo", "")
            category = outlier.get("category", "")
            score = outlier.get("score", 0.0)
            avg = outlier.get("avg_score", 0.0)
            delta = outlier.get("delta", 0.0)
            parts.append(
                f"- **{repo}** / {category}: {score:.0f}% "
                f"(platform avg: {avg:.0f}%, delta: {delta:.0f})"
            )

    # Consistency flags
    consistency = comparison.get("consistency", {})
    if consistency:
        parts.append("")
        parts.append("## Platform Consistency Flags")
        parts.append("")
        for flag, value in consistency.items():
            status = "YES" if value else "NO"
            label = flag.replace("_", " ").title()
            parts.append(f"- {label}: {status}")

    parts.append("")
    parts.append(
        "Based on the cross-repo summary above, provide your qualitative "
        "platform analysis as a JSON object matching the required schema."
    )

    return "\n".join(parts)


class CrossRepoAnalyzer:
    """Wraps the Anthropic API to run cross-repo qualitative analysis.

    Supports both direct API key auth and Vertex AI auth
    (via ANTHROPIC_VERTEX_PROJECT_ID environment variable).
    """

    def __init__(self, api_key: str | None = None, model: str = _DEFAULT_MODEL) -> None:
        self._api_key = api_key
        self._model = model

    def analyze(self, comparison: dict, fingerprints: list[dict]) -> dict:
        """Send comparison summary to Claude, return structured findings.

        Args:
            comparison: The dict returned by ``comparator.compare()``.
            fingerprints: The list of fingerprint dicts for all repos.

        Returns:
            Dict with keys ``strengths``, ``concerns``, ``patterns``,
            ``ai_readiness_notes``, and ``summary``.
            On any error returns a dict with a ``_error`` key and empty
            lists for all other keys.
        """
        try:
            import anthropic  # noqa: PLC0415 — intentional lazy import
        except ImportError:
            logger.error(
                "anthropic package not installed; install with: pip install anthropic==0.52.0"
            )
            result = dict(_EMPTY_FINDINGS)
            result["_error"] = "anthropic package not installed"
            return result

        import os
        vertex_project = os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID")
        if vertex_project:
            region = os.environ.get("ANTHROPIC_VERTEX_REGION", "europe-west1")
            client = anthropic.AnthropicVertex(project_id=vertex_project, region=region)
            model = os.environ.get("ANTHROPIC_DEFAULT_HAIKU_MODEL", self._model)
        else:
            client = anthropic.Anthropic(api_key=self._api_key)
            model = self._model

        user_message = _build_user_message(comparison, fingerprints)

        try:
            response = client.messages.create(
                model=model,
                max_tokens=4096,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
        except Exception as exc:
            logger.warning("Claude API call failed: %s", exc)
            result = dict(_EMPTY_FINDINGS)
            result["_error"] = f"API call failed: {exc}"
            return result

        raw_text = response.content[0].text if response.content else ""
        clean_text = _strip_fences(raw_text)

        try:
            findings = json.loads(clean_text)
        except json.JSONDecodeError as exc:
            logger.warning("Claude returned malformed JSON: %s", exc)
            result = dict(_EMPTY_FINDINGS)
            result["_error"] = f"Malformed JSON response: {exc}"
            result["_raw"] = raw_text
            return result

        for key in _EMPTY_FINDINGS:
            if key not in findings:
                findings[key] = _EMPTY_FINDINGS[key]

        return findings
