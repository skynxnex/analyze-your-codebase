"""Code quality checks using lizard, radon, and ruff."""
from __future__ import annotations

from pathlib import Path

from repoaudit.checks.base import Check, CheckResult

_CATEGORY = "code_quality"


class CodeQualityChecks(Check):
    """Code complexity, maintainability, and linting checks."""

    def run(self, repo_path: Path, language: dict) -> list[CheckResult]:
        lang = language.get("language", "unknown")
        results = [self._check_complexity(repo_path)]
        if "python" in lang:
            results.append(self._check_maintainability(repo_path))
            results.append(self._check_linting(repo_path))
        return results

    def _check_complexity(self, repo_path: Path) -> CheckResult:
        from repoaudit.tools.lizard_tool import run_lizard
        r = run_lizard(repo_path)
        if not r.ran:
            return CheckResult(
                name="code_complexity",
                category=_CATEGORY,
                passed=True,
                severity="optional",
                message="lizard not available — skipping complexity check",
            )
        if r.total_functions == 0:
            return CheckResult(
                name="code_complexity",
                category=_CATEGORY,
                passed=True,
                severity="optional",
                message="No functions found to analyse",
            )
        if r.functions_over_15 > 0:
            worst = ", ".join(
                f"{f['name']} (CCN {f['ccn']})" for f in r.worst_functions[:3]
            )
            return CheckResult(
                name="code_complexity",
                category=_CATEGORY,
                passed=False,
                severity="recommended",
                message=(
                    f"lizard: {r.functions_over_15} very complex function(s) (CCN>15) "
                    f"out of {r.total_functions} — avg CCN {r.avg_complexity}"
                ),
                detail=(
                    f"Most complex: {worst}\n"
                    "Consider breaking these down into smaller functions."
                ),
            )
        if r.functions_over_10 > 0:
            return CheckResult(
                name="code_complexity",
                category=_CATEGORY,
                passed=True,
                severity="recommended",
                message=(
                    f"lizard: {r.functions_over_10} complex function(s) (CCN>10) "
                    f"out of {r.total_functions} — avg CCN {r.avg_complexity}"
                ),
            )
        return CheckResult(
            name="code_complexity",
            category=_CATEGORY,
            passed=True,
            severity="optional",
            message=(
                f"lizard: all {r.total_functions} function(s) have acceptable complexity"
                f" — avg CCN {r.avg_complexity}"
            ),
        )

    def _check_maintainability(self, repo_path: Path) -> CheckResult:
        from repoaudit.tools.radon_tool import run_radon
        r = run_radon(repo_path)
        if not r.ran:
            return CheckResult(
                name="maintainability_index",
                category=_CATEGORY,
                passed=True,
                severity="optional",
                message="radon not available — skipping maintainability check",
            )
        if r.files_graded == 0:
            return CheckResult(
                name="maintainability_index",
                category=_CATEGORY,
                passed=True,
                severity="optional",
                message="No Python files found for maintainability analysis",
            )
        passed = r.grade in ("A", "B")
        return CheckResult(
            name="maintainability_index",
            category=_CATEGORY,
            passed=passed,
            severity="recommended",
            message=(
                f"radon maintainability: grade {r.grade} "
                f"({r.avg_maintainability}/100 avg across {r.files_graded} files)"
            ),
            detail=(
                ""
                if passed
                else (
                    "Low maintainability index. Consider reducing complexity, "
                    "adding docstrings, and shortening functions."
                )
            ),
        )

    def _check_linting(self, repo_path: Path) -> CheckResult:
        from repoaudit.tools.ruff_tool import run_ruff
        r = run_ruff(repo_path)
        if not r.ran:
            return CheckResult(
                name="linting_clean",
                category=_CATEGORY,
                passed=True,
                severity="optional",
                message="ruff not available — skipping lint check",
            )
        if r.error_count == 0 and r.warning_count == 0:
            return CheckResult(
                name="linting_clean",
                category=_CATEGORY,
                passed=True,
                severity="recommended",
                message="ruff: no lint issues found",
            )
        top_codes = sorted(r.by_code.items(), key=lambda x: x[1], reverse=True)[:3]
        codes_str = ", ".join(f"{c}\u00d7{n}" for c, n in top_codes)
        return CheckResult(
            name="linting_clean",
            category=_CATEGORY,
            passed=r.error_count == 0,
            severity="recommended",
            message=(
                f"ruff: {r.error_count} error(s), {r.warning_count} warning(s)"
                f" — top: {codes_str}"
            ),
            detail="\n".join(r.sample_messages[:5]) if r.sample_messages else "",
        )
