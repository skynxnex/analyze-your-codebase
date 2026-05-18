"""Tests for repoaudit.ai.formatter."""

from __future__ import annotations

import pytest

from repoaudit.ai.formatter import format_ai_section


_FULL_FINDINGS: dict = {
    "strengths": ["Clear module separation", "Consistent naming"],
    "concerns": ["No error handling in api.py", "Large functions in service.py"],
    "patterns": ["All handlers follow the same structure"],
    "ai_readiness_notes": ["Entry point is well-documented"],
    "summary": "Overall a solid codebase with some room for improvement.",
}


class TestFormatAiSection:
    def test_returns_markdown_string(self) -> None:
        result = format_ai_section(_FULL_FINDINGS)
        assert isinstance(result, str)

    def test_section_header_present(self) -> None:
        result = format_ai_section(_FULL_FINDINGS)
        assert "## AI Analysis" in result

    def test_model_label_present(self) -> None:
        result = format_ai_section(_FULL_FINDINGS)
        assert "claude-haiku-4-5-20251001" in result

    def test_strengths_rendered(self) -> None:
        result = format_ai_section(_FULL_FINDINGS)
        assert "Clear module separation" in result
        assert "Consistent naming" in result

    def test_concerns_rendered(self) -> None:
        result = format_ai_section(_FULL_FINDINGS)
        assert "No error handling in api.py" in result

    def test_patterns_rendered(self) -> None:
        result = format_ai_section(_FULL_FINDINGS)
        assert "All handlers follow the same structure" in result

    def test_ai_readiness_notes_rendered(self) -> None:
        result = format_ai_section(_FULL_FINDINGS)
        assert "Entry point is well-documented" in result

    def test_summary_rendered(self) -> None:
        result = format_ai_section(_FULL_FINDINGS)
        assert "Overall a solid codebase" in result

    def test_section_headers_present(self) -> None:
        result = format_ai_section(_FULL_FINDINGS)
        assert "### What's working well" in result
        assert "### Concerns" in result
        assert "### AI-Readiness Notes" in result
        assert "### Patterns observed" in result
        assert "### Summary" in result


class TestEmptyListsGracefulDegradation:
    def test_empty_strengths_shows_fallback(self) -> None:
        findings = dict(_FULL_FINDINGS)
        findings["strengths"] = []
        result = format_ai_section(findings)
        assert "No specific strengths identified" in result

    def test_empty_concerns_shows_fallback(self) -> None:
        findings = dict(_FULL_FINDINGS)
        findings["concerns"] = []
        result = format_ai_section(findings)
        assert "No specific concerns identified" in result

    def test_empty_patterns_shows_fallback(self) -> None:
        findings = dict(_FULL_FINDINGS)
        findings["patterns"] = []
        result = format_ai_section(findings)
        assert "No cross-cutting patterns identified" in result

    def test_empty_ai_readiness_shows_fallback(self) -> None:
        findings = dict(_FULL_FINDINGS)
        findings["ai_readiness_notes"] = []
        result = format_ai_section(findings)
        assert "No specific AI-readiness observations" in result

    def test_empty_summary_shows_fallback(self) -> None:
        findings = dict(_FULL_FINDINGS)
        findings["summary"] = ""
        result = format_ai_section(findings)
        assert "No summary available." in result


class TestMissingKeysGracefulDegradation:
    def test_completely_empty_dict_does_not_crash(self) -> None:
        result = format_ai_section({})
        assert "## AI Analysis" in result

    def test_missing_strengths_key_shows_fallback(self) -> None:
        findings = {k: v for k, v in _FULL_FINDINGS.items() if k != "strengths"}
        result = format_ai_section(findings)
        assert "No specific strengths identified" in result

    def test_missing_concerns_key_shows_fallback(self) -> None:
        findings = {k: v for k, v in _FULL_FINDINGS.items() if k != "concerns"}
        result = format_ai_section(findings)
        assert "No specific concerns identified" in result

    def test_missing_summary_key_shows_fallback(self) -> None:
        findings = {k: v for k, v in _FULL_FINDINGS.items() if k != "summary"}
        result = format_ai_section(findings)
        assert "No summary available." in result


class TestErrorFindings:
    def test_error_key_shows_warning(self) -> None:
        findings = {"_error": "API call failed: timeout"}
        result = format_ai_section(findings)
        assert "Warning" in result
        assert "API call failed: timeout" in result

    def test_error_with_raw_shows_details_block(self) -> None:
        findings = {"_error": "Malformed JSON response", "_raw": "not json at all"}
        result = format_ai_section(findings)
        assert "not json at all" in result

    def test_error_does_not_render_normal_sections(self) -> None:
        findings = {"_error": "some error", "strengths": ["should not appear"]}
        result = format_ai_section(findings)
        assert "should not appear" not in result
        assert "### What's working well" not in result
