"""Developer-experience checks.

Checks for: docker-compose.yml, Dockerfile, seed script, local setup docs,
and a Makefile / yarn script runner.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from repoaudit.checks.base import Check, CheckResult

_CATEGORY = "devex"

_SETUP_KEYWORDS = re.compile(
    r"(?:getting started|local setup|local development|running locally|how to run|setup)",
    re.IGNORECASE,
)


class DevExChecks(Check):
    """All developer-experience checks bundled into one group."""

    def run(self, repo_path: Path, language: dict) -> list[CheckResult]:
        return [
            self._check_docker_compose(repo_path),
            self._check_dockerfile(repo_path),
            self._check_seed_script(repo_path),
            self._check_local_setup_documented(repo_path),
            self._check_makefile_or_yarn(repo_path),
        ]

    def _check_docker_compose(self, repo_path: Path) -> CheckResult:
        candidates = [
            repo_path / "docker-compose.yml",
            repo_path / "docker-compose.yaml",
        ]
        found = next((p for p in candidates if p.exists()), None)
        return CheckResult(
            name="docker_compose_exists",
            category=_CATEGORY,
            passed=found is not None,
            severity="required",
            message=(
                f"docker-compose file found: {found.name}"
                if found
                else "No docker-compose.yml found"
            ),
            detail=(
                ""
                if found
                else "Add a docker-compose.yml so contributors can spin up the full stack with one command."
            ),
        )

    def _check_dockerfile(self, repo_path: Path) -> CheckResult:
        dockerfiles = list(repo_path.glob("Dockerfile*"))
        found = bool(dockerfiles)
        return CheckResult(
            name="dockerfile_exists",
            category=_CATEGORY,
            passed=found,
            severity="required",
            message=(
                f"Dockerfile found: {dockerfiles[0].name}"
                if found
                else "No Dockerfile found"
            ),
            detail=(
                ""
                if found
                else "Add a Dockerfile to make the service runnable anywhere without local dependency installation."
            ),
        )

    def _check_seed_script(self, repo_path: Path) -> CheckResult:
        # Check for standalone seed scripts.
        seed_globs = [
            "seed*.py", "*seed.py", "seed*.sh", "*seed.sh",
            "db_seed*", "*db_seed*",
        ]
        for pattern in seed_globs:
            matches = list(repo_path.glob(pattern))
            if matches:
                return CheckResult(
                    name="seed_script_exists",
                    category=_CATEGORY,
                    passed=True,
                    severity="recommended",
                    message=f"Seed script found: {matches[0].name}",
                )

        # Check Makefile for seed target.
        makefile = repo_path / "Makefile"
        if makefile.exists():
            text = makefile.read_text(encoding="utf-8", errors="ignore").lower()
            if "seed" in text:
                return CheckResult(
                    name="seed_script_exists",
                    category=_CATEGORY,
                    passed=True,
                    severity="recommended",
                    message="Seed target found in Makefile",
                )

        # Check package.json scripts for seed.
        pkg = repo_path / "package.json"
        if pkg.exists():
            try:
                data = json.loads(pkg.read_text(encoding="utf-8", errors="ignore"))
                scripts = data.get("scripts", {})
                if any("seed" in key.lower() or "seed" in str(val).lower()
                       for key, val in scripts.items()):
                    return CheckResult(
                        name="seed_script_exists",
                        category=_CATEGORY,
                        passed=True,
                        severity="recommended",
                        message="Seed script found in package.json scripts",
                    )
            except json.JSONDecodeError:
                pass

        return CheckResult(
            name="seed_script_exists",
            category=_CATEGORY,
            passed=False,
            severity="recommended",
            message="No seed script found",
            detail=(
                "Add a seed script (e.g. seed.py, db_seed.sh) to populate local dev data. "
                "This dramatically reduces onboarding time."
            ),
        )

    def _check_local_setup_documented(self, repo_path: Path) -> CheckResult:
        readme = repo_path / "readme.md"
        # Case-insensitive filename search.
        readme_files = list(repo_path.glob("[Rr][Ee][Aa][Dd][Mm][Ee]*"))
        for rf in readme_files:
            if not rf.is_file():
                continue
            text = rf.read_text(encoding="utf-8", errors="ignore")
            if _SETUP_KEYWORDS.search(text):
                return CheckResult(
                    name="local_setup_documented",
                    category=_CATEGORY,
                    passed=True,
                    severity="recommended",
                    message=f"Local setup section found in {rf.name}",
                )

        # Also check CONTRIBUTING.md.
        contributing = repo_path / "CONTRIBUTING.md"
        if contributing.exists():
            text = contributing.read_text(encoding="utf-8", errors="ignore")
            if _SETUP_KEYWORDS.search(text):
                return CheckResult(
                    name="local_setup_documented",
                    category=_CATEGORY,
                    passed=True,
                    severity="recommended",
                    message="Local setup section found in CONTRIBUTING.md",
                )

        return CheckResult(
            name="local_setup_documented",
            category=_CATEGORY,
            passed=False,
            severity="recommended",
            message="No local setup section found in README or CONTRIBUTING.md",
            detail=(
                "Add a 'Getting Started' or 'Local Development' section to your README.md "
                "explaining how to run the service locally."
            ),
        )

    def _check_makefile_or_yarn(self, repo_path: Path) -> CheckResult:
        has_makefile = (repo_path / "Makefile").exists()
        has_pkg = (repo_path / "package.json").exists()

        if has_makefile:
            return CheckResult(
                name="makefile_or_yarn",
                category=_CATEGORY,
                passed=True,
                severity="optional",
                message="Makefile found",
            )

        if has_pkg:
            try:
                data = json.loads(
                    (repo_path / "package.json").read_text(encoding="utf-8", errors="ignore")
                )
                if data.get("scripts"):
                    return CheckResult(
                        name="makefile_or_yarn",
                        category=_CATEGORY,
                        passed=True,
                        severity="optional",
                        message="package.json scripts found",
                    )
            except json.JSONDecodeError:
                pass

        return CheckResult(
            name="makefile_or_yarn",
            category=_CATEGORY,
            passed=False,
            severity="optional",
            message="No Makefile or package.json scripts found",
            detail="Consider adding a Makefile or package.json scripts for common dev tasks.",
        )
