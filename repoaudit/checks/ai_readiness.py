"""AI-readiness checks.

Checks whether a repository is well-prepared for AI-assisted development:
good CLAUDE.md / AI instructions, a substantial README, consistent file naming,
env-var documentation, and explicit dependency documentation.
"""

from __future__ import annotations

import re
from pathlib import Path

from repoaudit.checks.base import Check, CheckResult

_CATEGORY = "ai_readiness"

# Matches camelCase filenames (at least one lowercase after an uppercase).
_CAMEL_RE = re.compile(r"^[a-z]+[A-Z][a-zA-Z0-9]*(\.[a-z]+)?$")
# Matches snake_case filenames.
_SNAKE_RE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)+(\.[a-z]+)?$")


class AIReadinessChecks(Check):
    """All AI-readiness checks bundled into one group."""

    def run(self, repo_path: Path, language: dict) -> list[CheckResult]:
        return [
            self._check_claude_md(repo_path),
            self._check_readme_substantial(repo_path),
            self._check_naming_consistent(repo_path),
            self._check_env_vars_documented(repo_path),
            self._check_dependencies_explicit(repo_path),
        ]

    def _check_claude_md(self, repo_path: Path) -> CheckResult:
        candidates = [
            repo_path / "CLAUDE.md",
            repo_path / ".claude" / "instructions.md",
        ]
        found = any(p.exists() for p in candidates)
        return CheckResult(
            name="claude_md_exists",
            category=_CATEGORY,
            passed=found,
            severity="required",
            message="CLAUDE.md found" if found else "No CLAUDE.md found",
            detail=(
                ""
                if found
                else (
                    "Add a CLAUDE.md with service description, entry points, "
                    "env vars, and how to run tests. This enables AI assistants "
                    "to understand and contribute to the codebase immediately."
                )
            ),
        )

    def _check_readme_substantial(self, repo_path: Path) -> CheckResult:
        readme = repo_path / "README.md"
        if not readme.exists():
            return CheckResult(
                name="readme_substantial",
                category=_CATEGORY,
                passed=False,
                severity="required",
                message="No README.md found",
                detail="Add a README.md with at least 30 lines covering purpose, setup, and usage.",
            )
        lines = [
            ln for ln in readme.read_text(encoding="utf-8", errors="ignore").splitlines()
            if ln.strip()
        ]
        passed = len(lines) >= 30
        return CheckResult(
            name="readme_substantial",
            category=_CATEGORY,
            passed=passed,
            severity="required",
            message=f"README.md has {len(lines)} non-blank lines",
            detail=(
                ""
                if passed
                else "README.md is too short. Expand it to at least 30 lines."
            ),
        )

    def _check_naming_consistent(self, repo_path: Path) -> CheckResult:
        """Warn when both camelCase and snake_case files coexist in the same dir."""
        violations: list[str] = []
        # Check each directory up to 2 levels deep.
        dirs_to_check = [repo_path] + [
            d for d in repo_path.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ]
        for directory in dirs_to_check:
            try:
                filenames = [
                    f.name for f in directory.iterdir()
                    if f.is_file() and not f.name.startswith(".")
                ]
            except PermissionError:
                continue
            has_camel = any(_CAMEL_RE.match(n) for n in filenames)
            has_snake = any(_SNAKE_RE.match(n) for n in filenames)
            if has_camel and has_snake:
                violations.append(str(directory.relative_to(repo_path) or "."))

        passed = not violations
        return CheckResult(
            name="naming_consistent",
            category=_CATEGORY,
            passed=passed,
            severity="recommended",
            message=(
                "File naming is consistent"
                if passed
                else f"Mixed camelCase and snake_case in: {', '.join(violations)}"
            ),
            detail=(
                ""
                if passed
                else "Pick one convention (snake_case preferred for Python, camelCase for JS/TS)."
            ),
        )

    def _check_env_vars_documented(self, repo_path: Path) -> CheckResult:
        has_example = (
            (repo_path / ".env.example").exists()
            or (repo_path / "env.example").exists()
            or (repo_path / ".env.sample").exists()
        )
        has_dotenv = (repo_path / ".env").exists()

        if has_example:
            return CheckResult(
                name="env_vars_documented",
                category=_CATEGORY,
                passed=True,
                severity="recommended",
                message=".env.example found — env vars are documented",
            )
        if has_dotenv:
            return CheckResult(
                name="env_vars_documented",
                category=_CATEGORY,
                passed=False,
                severity="recommended",
                message=".env exists but no .env.example",
                detail="Add a .env.example (with placeholder values) so contributors know what vars are needed.",
            )
        return CheckResult(
            name="env_vars_documented",
            category=_CATEGORY,
            passed=True,
            severity="recommended",
            message="No .env file found — env var docs not applicable",
        )

    def _check_dependencies_explicit(self, repo_path: Path) -> CheckResult:
        candidates = [
            repo_path / "README.md",
            repo_path / "DEPENDENCIES.md",
            repo_path / "docs" / "DEPENDENCIES.md",
        ]
        keywords = ["depend", "service", "postgresql", "redis", "kafka", "rabbitmq", "mysql"]
        for candidate in candidates:
            if not candidate.exists():
                continue
            text = candidate.read_text(encoding="utf-8", errors="ignore").lower()
            if any(kw in text for kw in keywords):
                return CheckResult(
                    name="dependencies_explicit",
                    category=_CATEGORY,
                    passed=True,
                    severity="optional",
                    message=f"Service dependencies documented in {candidate.name}",
                )
        return CheckResult(
            name="dependencies_explicit",
            category=_CATEGORY,
            passed=False,
            severity="optional",
            message="No explicit service dependency documentation found",
            detail=(
                "Consider adding a DEPENDENCIES.md or a 'Dependencies' section in README.md "
                "listing external services (databases, queues, APIs)."
            ),
        )
