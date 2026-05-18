"""Claude API wrapper for qualitative codebase analysis."""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM_PROMPT = """\
You are an expert code reviewer performing qualitative analysis of a codebase.
You will receive a static analysis fingerprint and samples of actual source code.

Your job is to find what static analysis cannot: consistency, domain boundary clarity,
error handling patterns, naming quality, and overall AI-friendliness.

When evaluating AI-readiness, ask: "Could an AI agent confidently add a new feature
to this codebase without breaking things or getting confused?"

Guidelines:
- Be specific. Cite file names or concrete patterns you observed.
- Be honest about both strengths and weaknesses.
- Focus only on what you can actually see in the samples provided.
- Do not invent issues you cannot support with evidence from the samples.

Return ONLY valid JSON — no markdown fences, no explanation text, nothing outside the JSON object.

The JSON must have exactly these keys:
{
  "strengths": ["list of specific things done well"],
  "concerns": ["list of specific issues found in the code"],
  "patterns": ["cross-cutting observations about consistency, style, architecture"],
  "ai_readiness_notes": ["specific observations about how AI-friendly the codebase is"],
  "summary": "2-3 sentence overall assessment"
}
"""

def _strip_fences(text: str) -> str:
    """Strip markdown code fences from a string if present."""
    clean = text.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[-1]
        if clean.endswith("```"):
            clean = clean.rsplit("```", 1)[0]
        clean = clean.strip()
    return clean


_EMPTY_FINDINGS: dict = {
    "strengths": [],
    "concerns": [],
    "patterns": [],
    "ai_readiness_notes": [],
    "summary": "",
}


def _build_user_message(fingerprint: dict, samples: list[dict]) -> str:
    """Compose the user-turn message from fingerprint data and code samples."""
    parts: list[str] = []

    parts.append("## Static Analysis Fingerprint")
    parts.append("")
    parts.append(f"Repository: {fingerprint.get('repo_name', 'unknown')}")
    parts.append(f"Language: {fingerprint.get('language', {}).get('language', 'unknown')}")

    scores = fingerprint.get("score", {})
    parts.append("")
    parts.append("### Scores")
    for key, val in scores.items():
        parts.append(f"- {key}: {val:.1f}" if isinstance(val, float) else f"- {key}: {val}")

    results = fingerprint.get("check_results", [])
    failed = [r for r in results if not r.get("passed")]
    if failed:
        parts.append("")
        parts.append("### Failed checks")
        for r in failed:
            parts.append(f"- [{r.get('severity', '')}] {r.get('name', '')}: {r.get('message', '')}")

    parts.append("")
    parts.append("## Sampled Source Files")

    for sample in samples:
        parts.append("")
        parts.append(f"### {sample['path']} (role: {sample['role']})")
        parts.append("```")
        parts.append(sample.get("content", ""))
        parts.append("```")

    parts.append("")
    parts.append(
        "Based on the fingerprint and code samples above, provide your qualitative analysis "
        "as a JSON object matching the required schema."
    )

    return "\n".join(parts)


class ClaudeAnalyzer:
    """Wraps the Anthropic API to run qualitative analysis on a repo.

    Supports both direct API key auth and Vertex AI auth
    (via ANTHROPIC_VERTEX_PROJECT_ID environment variable).
    """

    def __init__(self, api_key: str | None = None, model: str = _DEFAULT_MODEL) -> None:
        self._api_key = api_key
        self._model = model

    def analyze(self, fingerprint: dict, samples: list[dict]) -> dict:
        """Send fingerprint + code samples to Claude, return structured findings.

        Returns:
            Dict with keys ``strengths``, ``concerns``, ``patterns``,
            ``ai_readiness_notes``, and ``summary``.
            On any error (network, parse, etc.) returns a dict with a
            ``_error`` key and empty lists for all other keys.

        Raises:
            Nothing — all errors are caught and returned as ``_error`` entries.
        """
        try:
            import anthropic  # noqa: PLC0415 — intentional lazy import
        except ImportError:
            logger.error("anthropic package not installed; install with: pip install anthropic==0.52.0")
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

        user_message = _build_user_message(fingerprint, samples)

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

        # Strip markdown code fences if model wrapped the JSON despite instructions.
        clean_text = _strip_fences(raw_text)

        try:
            findings = json.loads(clean_text)
        except json.JSONDecodeError as exc:
            logger.warning("Claude returned malformed JSON: %s", exc)
            result = dict(_EMPTY_FINDINGS)
            result["_error"] = f"Malformed JSON response: {exc}"
            result["_raw"] = raw_text
            return result

        # Ensure all expected keys exist (graceful degradation).
        for key in _EMPTY_FINDINGS:
            if key not in findings:
                findings[key] = _EMPTY_FINDINGS[key]

        return findings
