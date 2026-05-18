"""Security checks.

Covers: hardcoded secrets, committed .env files, unpinned dependencies,
and Docker images using the 'latest' tag.
"""

from __future__ import annotations

import re
from pathlib import Path

from repoaudit.checks.base import Check, CheckResult

_CATEGORY = "security"

# Patterns that suggest hardcoded secrets — match key=value / key: value in
# source files. We look for common secret-like key names assigned to string
# literals. False positives are possible; the check is intentionally broad.
_SECRET_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"""(?:password|passwd|pwd)\s*=\s*['"][^'"]{4,}['"]""",
        r"""(?:secret|api_key|apikey|api_secret)\s*=\s*['"][^'"]{4,}['"]""",
        r"""(?:token|access_token|auth_token)\s*=\s*['"][^'"]{4,}['"]""",
        r"""(?:password|passwd|secret|api_key|token)\s*:\s*['"][^'"]{4,}['"]""",
    ]
]

# File extensions to scan for hardcoded secrets.
_SOURCE_EXTENSIONS = {
    ".py", ".js", ".ts", ".go", ".java", ".kt", ".cs",
    ".rb", ".php", ".sh", ".yaml", ".yml", ".toml", ".env",
}

# Extensions / paths to skip.
_SKIP_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".tox",
    # Build output — compiled artefacts, not source code
    "build", "target", "dist", "out", "bin", "obj", ".gradle",
}

# Directories that are expected to contain literal secret-like strings as test
# fixtures — exclude them from the hardcoded-secrets scan.
_SKIP_TEST_DIRS = {"tests", "test", "__tests__", "spec"}

# Patterns for floating (unpinned) versions in requirements.txt.
# A line is floating if it names a package but has no == pin.
_REQUIREMENTS_PINNED_RE = re.compile(
    r"^\s*[A-Za-z0-9_\-\[\].]+\s*==\s*\S+"
)
_REQUIREMENTS_COMMENT_OR_BLANK = re.compile(r"^\s*(#|$)")


class SecurityChecks(Check):
    """All security checks bundled into one group."""

    def run(self, repo_path: Path, language: dict) -> list[CheckResult]:
        return [
            self._check_no_hardcoded_secrets(repo_path),
            self._check_no_dotenv_committed(repo_path),
            self._check_deps_pinned(repo_path, language),
            self._check_no_latest_docker(repo_path),
        ]

    def _check_no_hardcoded_secrets(self, repo_path: Path) -> CheckResult:
        hits: list[str] = []
        for path in self._source_files(repo_path):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pattern in _SECRET_PATTERNS:
                if pattern.search(text):
                    hits.append(str(path.relative_to(repo_path)))
                    break  # one hit per file is enough

        passed = not hits
        return CheckResult(
            name="no_hardcoded_secrets",
            category=_CATEGORY,
            passed=passed,
            severity="required",
            message=(
                "No hardcoded secrets detected"
                if passed
                else f"Possible hardcoded secrets in {len(hits)} file(s): {', '.join(hits[:5])}"
            ),
            detail=(
                ""
                if passed
                else "Move secrets to environment variables or a secrets manager."
            ),
        )

    def _check_no_dotenv_committed(self, repo_path: Path) -> CheckResult:
        dotenv = repo_path / ".env"
        if not dotenv.exists():
            return CheckResult(
                name="no_dotenv_committed",
                category=_CATEGORY,
                passed=True,
                severity="required",
                message="No .env file in repo root",
            )

        gitignore = repo_path / ".gitignore"
        ignored = False
        if gitignore.exists():
            text = gitignore.read_text(encoding="utf-8", errors="ignore")
            ignored = any(
                line.strip() in {".env", "/.env", ".env*"}
                for line in text.splitlines()
            )

        if ignored:
            return CheckResult(
                name="no_dotenv_committed",
                category=_CATEGORY,
                passed=True,
                severity="required",
                message=".env exists but is listed in .gitignore",
            )
        return CheckResult(
            name="no_dotenv_committed",
            category=_CATEGORY,
            passed=False,
            severity="required",
            message=".env file exists and is NOT in .gitignore",
            detail="Add '.env' to .gitignore to prevent accidental secret commits.",
        )

    def _check_deps_pinned(self, repo_path: Path, language: dict) -> CheckResult:
        lang = language.get("language", "unknown")

        if "python" in lang:
            return self._check_requirements_pinned(repo_path)
        if "typescript" in lang or "kotlin" in lang:
            return self._check_package_json_pinned(repo_path)
        if lang == "go":
            return self._check_gomod_pinned(repo_path)
        if lang == "dotnet":
            # .NET uses NuGet — version management is in *.csproj.
            # We trust the existing tooling; mark as pass with a note.
            return CheckResult(
                name="deps_pinned",
                category=_CATEGORY,
                passed=True,
                severity="required",
                message=".NET project detected — NuGet versions assumed managed in .csproj",
            )

        return CheckResult(
            name="deps_pinned",
            category=_CATEGORY,
            passed=True,
            severity="required",
            message="No recognised dependency file found to audit",
        )

    def _check_requirements_pinned(self, repo_path: Path) -> CheckResult:
        req = repo_path / "requirements.txt"
        if not req.exists():
            return CheckResult(
                name="deps_pinned",
                category=_CATEGORY,
                passed=True,
                severity="required",
                message="No requirements.txt found",
            )
        unpinned: list[str] = []
        for line in req.read_text(encoding="utf-8", errors="ignore").splitlines():
            if _REQUIREMENTS_COMMENT_OR_BLANK.match(line):
                continue
            # Lines with -r, -c, --index-url, etc.
            if line.strip().startswith("-"):
                continue
            if not _REQUIREMENTS_PINNED_RE.match(line):
                unpinned.append(line.strip())

        passed = not unpinned
        return CheckResult(
            name="deps_pinned",
            category=_CATEGORY,
            passed=passed,
            severity="required",
            message=(
                "All requirements.txt entries are pinned"
                if passed
                else f"{len(unpinned)} unpinned entries: {', '.join(unpinned[:5])}"
            ),
            detail=(
                ""
                if passed
                else "Pin every package to an exact version (e.g. requests==2.31.0)."
            ),
        )

    def _check_package_json_pinned(self, repo_path: Path) -> CheckResult:
        import json

        pkg = repo_path / "package.json"
        if not pkg.exists():
            return CheckResult(
                name="deps_pinned",
                category=_CATEGORY,
                passed=True,
                severity="required",
                message="No package.json found",
            )
        try:
            data = json.loads(pkg.read_text(encoding="utf-8", errors="ignore"))
        except json.JSONDecodeError:
            return CheckResult(
                name="deps_pinned",
                category=_CATEGORY,
                passed=False,
                severity="required",
                message="package.json is not valid JSON",
            )
        unpinned: list[str] = []
        for section in ("dependencies", "devDependencies"):
            for pkg_name, version in data.get(section, {}).items():
                if isinstance(version, str) and (
                    version.startswith("^")
                    or version.startswith("~")
                    or version == "*"
                    or version.startswith(">=")
                    or version.startswith(">")
                ):
                    unpinned.append(f"{pkg_name}@{version}")

        passed = not unpinned
        return CheckResult(
            name="deps_pinned",
            category=_CATEGORY,
            passed=passed,
            severity="required",
            message=(
                "All package.json dependencies are pinned"
                if passed
                else f"{len(unpinned)} unpinned: {', '.join(unpinned[:5])}"
            ),
            detail=(
                ""
                if passed
                else "Use exact versions (e.g. '4.17.21') instead of ranges ('^4.0.0')."
            ),
        )

    def _check_gomod_pinned(self, repo_path: Path) -> CheckResult:
        gomod = repo_path / "go.mod"
        if not gomod.exists():
            return CheckResult(
                name="deps_pinned",
                category=_CATEGORY,
                passed=True,
                severity="required",
                message="No go.mod found",
            )
        text = gomod.read_text(encoding="utf-8", errors="ignore")
        # go.mod require blocks: each dep should have a version.
        missing: list[str] = []
        in_require = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("require ("):
                in_require = True
                continue
            if in_require and stripped == ")":
                in_require = False
                continue
            if in_require and stripped and not stripped.startswith("//"):
                parts = stripped.split()
                if len(parts) < 2:
                    missing.append(stripped)

        passed = not missing
        return CheckResult(
            name="deps_pinned",
            category=_CATEGORY,
            passed=passed,
            severity="required",
            message=(
                "go.mod dependencies appear versioned"
                if passed
                else f"Some go.mod entries may lack versions: {', '.join(missing[:5])}"
            ),
        )

    def _check_no_latest_docker(self, repo_path: Path) -> CheckResult:
        docker_files = [
            repo_path / "Dockerfile",
            repo_path / "docker-compose.yml",
            repo_path / "docker-compose.yaml",
        ]
        hits: list[str] = []
        for df in docker_files:
            if not df.exists():
                continue
            text = df.read_text(encoding="utf-8", errors="ignore")
            # Match "image: foo:latest" or "FROM foo:latest"
            if re.search(r"(?:image:\s*|FROM\s+)\S+:latest", text, re.IGNORECASE):
                hits.append(df.name)

        passed = not hits
        return CheckResult(
            name="no_latest_docker",
            category=_CATEGORY,
            passed=passed,
            severity="recommended",
            message=(
                "No Docker images use ':latest' tag"
                if passed
                else f"':latest' tag found in: {', '.join(hits)}"
            ),
            detail=(
                ""
                if passed
                else "Pin Docker images to specific versions (e.g. python:3.11-slim, not python:latest)."
            ),
        )

    def _source_files(self, repo_path: Path):
        """Yield source files to scan, skipping irrelevant directories."""
        for path in repo_path.rglob("*"):
            if path.is_dir():
                continue
            if any(skip in path.parts for skip in _SKIP_DIRS):
                continue
            # Skip test directories — they legitimately contain literal secret-
            # like strings as test fixtures, which would cause false positives.
            if any(part in _SKIP_TEST_DIRS for part in path.parts):
                continue
            if path.suffix.lower() in _SOURCE_EXTENSIONS:
                yield path
