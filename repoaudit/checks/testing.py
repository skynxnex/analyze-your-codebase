"""Testing checks.

Language-aware checks for: test directory existence, test config files,
behaviour-driven test naming, and CI that runs tests.
"""

from __future__ import annotations

import re
from pathlib import Path

from repoaudit.checks.base import Check, CheckResult

_CATEGORY = "testing"

# Patterns that suggest behaviour-driven test naming.
_BEHAVIOR_TEST_RE = re.compile(
    r"(?:def test_should_|def test_when_|def test_given_|it\(|describe\(|should\()",
    re.IGNORECASE,
)


class TestingChecks(Check):
    """All testing checks bundled into one group."""

    def run(self, repo_path: Path, language: dict) -> list[CheckResult]:
        lang = language.get("language", "unknown")
        ci_files = self._find_ci_files(repo_path)
        return [
            self._check_tests_exist(repo_path),
            self._check_test_config(repo_path, lang),
            self._check_tests_named_for_behavior(repo_path, lang),
            self._check_ci_exists(ci_files),
            self._check_ci_runs_tests(ci_files),
        ]

    def _check_tests_exist(self, repo_path: Path) -> CheckResult:
        candidates = [
            repo_path / "tests",
            repo_path / "test",
            repo_path / "__tests__",
            repo_path / "spec",
            # JVM/Spring convention
            repo_path / "src" / "test" / "kotlin",
            repo_path / "src" / "test" / "java",
        ]
        found = next((p for p in candidates if p.is_dir()), None)

        # Also accept a flat test file in root (common in Go).
        if found is None:
            flat = list(repo_path.glob("*_test.go"))
            if flat:
                return CheckResult(
                    name="tests_exist",
                    category=_CATEGORY,
                    passed=True,
                    severity="required",
                    message=f"Go test files found (e.g. {flat[0].name})",
                )

        # Fallback: search recursively for test files nested under src/ or similar.
        # Covers patterns like src/utils/tests/, src/models/__tests__/.
        if found is None:
            skip = {"node_modules", ".venv", "venv", "__pycache__", ".git", "build", "target", "dist"}
            patterns = ["*.test.js", "*.spec.js", "*.test.ts", "*.spec.ts",
                        "*.test.tsx", "*.spec.tsx", "test_*.py"]
            for pattern in patterns:
                matches = [
                    p for p in repo_path.rglob(pattern)
                    if not any(s in p.parts for s in skip)
                ]
                if matches:
                    rel = matches[0].relative_to(repo_path)
                    return CheckResult(
                        name="tests_exist",
                        category=_CATEGORY,
                        passed=True,
                        severity="required",
                        message=f"Test files found (e.g. {rel})",
                    )

        return CheckResult(
            name="tests_exist",
            category=_CATEGORY,
            passed=found is not None,
            severity="required",
            message=(
                f"Test directory found: {found.name}/"
                if found
                else "No tests/ or test/ directory found"
            ),
            detail=(
                ""
                if found
                else "Create a tests/ directory and add test files covering core behaviour."
            ),
        )

    def _check_test_config(self, repo_path: Path, lang: str) -> CheckResult:
        if "python" in lang:
            return self._test_config_python(repo_path)
        if "typescript" in lang:
            return self._test_config_typescript(repo_path)
        if "kotlin" in lang or lang == "dotnet":
            # Gradle / MSBuild handles test config; assume present.
            return CheckResult(
                name="test_config_exists",
                category=_CATEGORY,
                passed=True,
                severity="recommended",
                message=f"{'Kotlin/Gradle' if 'kotlin' in lang else '.NET/MSBuild'} — test config managed by build tool",
            )
        if lang == "go":
            return CheckResult(
                name="test_config_exists",
                category=_CATEGORY,
                passed=True,
                severity="recommended",
                message="Go — test runner is built-in (go test)",
            )
        if lang == "nodejs":
            return self._test_config_nodejs(repo_path)
        # Generic fallback.
        return CheckResult(
            name="test_config_exists",
            category=_CATEGORY,
            passed=True,
            severity="recommended",
            message="Language not recognised — skipping test config check",
        )

    def _test_config_python(self, repo_path: Path) -> CheckResult:
        # pytest.ini, setup.cfg with [tool:pytest], pyproject.toml with [tool.pytest.ini_options]
        if (repo_path / "pytest.ini").exists():
            return CheckResult(
                name="test_config_exists",
                category=_CATEGORY,
                passed=True,
                severity="recommended",
                message="pytest.ini found",
            )
        setup_cfg = repo_path / "setup.cfg"
        if setup_cfg.exists():
            text = setup_cfg.read_text(encoding="utf-8", errors="ignore")
            if "[tool:pytest]" in text or "[pytest]" in text:
                return CheckResult(
                    name="test_config_exists",
                    category=_CATEGORY,
                    passed=True,
                    severity="recommended",
                    message="pytest config found in setup.cfg",
                )
        pyproject = repo_path / "pyproject.toml"
        if pyproject.exists():
            text = pyproject.read_text(encoding="utf-8", errors="ignore")
            if "[tool.pytest" in text:
                return CheckResult(
                    name="test_config_exists",
                    category=_CATEGORY,
                    passed=True,
                    severity="recommended",
                    message="pytest config found in pyproject.toml",
                )
        return CheckResult(
            name="test_config_exists",
            category=_CATEGORY,
            passed=False,
            severity="recommended",
            message="No pytest config found (pytest.ini / setup.cfg / pyproject.toml)",
            detail="Add [tool.pytest.ini_options] to pyproject.toml to configure pytest.",
        )

    def _test_config_nodejs(self, repo_path: Path) -> CheckResult:
        """Check for jest/mocha/vitest config or test script in package.json."""
        import json

        # Explicit config files
        if list(repo_path.glob("jest.config.*")) or list(repo_path.glob("vitest.config.*")):
            found = next(
                p.name for p in (
                    list(repo_path.glob("jest.config.*")) + list(repo_path.glob("vitest.config.*"))
                )
            )
            return CheckResult(
                name="test_config_exists",
                category=_CATEGORY,
                passed=True,
                severity="recommended",
                message=f"Test config found: {found}",
            )
        # Check package.json scripts for a test runner
        pkg = repo_path / "package.json"
        if pkg.exists():
            try:
                data = json.loads(pkg.read_text(encoding="utf-8", errors="ignore"))
                test_script = data.get("scripts", {}).get("test", "")
                if any(runner in test_script for runner in ("jest", "mocha", "vitest", "tap", "ava")):
                    return CheckResult(
                        name="test_config_exists",
                        category=_CATEGORY,
                        passed=True,
                        severity="recommended",
                        message=f"Test runner found in package.json scripts: {test_script[:60]}",
                    )
            except (json.JSONDecodeError, OSError):
                pass
        return CheckResult(
            name="test_config_exists",
            category=_CATEGORY,
            passed=False,
            severity="recommended",
            message="No jest/mocha/vitest config or test script found",
            detail="Add a jest.config.js or vitest.config.ts, or add a 'test' script to package.json.",
        )

    def _test_config_typescript(self, repo_path: Path) -> CheckResult:
        vitest = list(repo_path.glob("vitest.config.*"))
        jest = list(repo_path.glob("jest.config.*"))
        if vitest:
            return CheckResult(
                name="test_config_exists",
                category=_CATEGORY,
                passed=True,
                severity="recommended",
                message=f"vitest config found: {vitest[0].name}",
            )
        if jest:
            return CheckResult(
                name="test_config_exists",
                category=_CATEGORY,
                passed=True,
                severity="recommended",
                message=f"jest config found: {jest[0].name}",
            )
        return CheckResult(
            name="test_config_exists",
            category=_CATEGORY,
            passed=False,
            severity="recommended",
            message="No vitest.config.* or jest.config.* found",
            detail="Add a vitest.config.ts or jest.config.js to configure your test runner.",
        )

    def _check_tests_named_for_behavior(self, repo_path: Path, lang: str) -> CheckResult:
        """Sample up to 20 test files and check for behaviour-driven naming."""
        test_dirs = [
            repo_path / "tests",
            repo_path / "test",
            repo_path / "__tests__",
        ]
        test_files: list[Path] = []
        for td in test_dirs:
            if td.is_dir():
                test_files.extend(list(td.rglob("test_*.py"))[:10])
                test_files.extend(list(td.rglob("*.test.ts"))[:10])
                test_files.extend(list(td.rglob("*.spec.ts"))[:10])
                test_files.extend(list(td.rglob("*.test.tsx"))[:10])

        # Also pick up JS test files and JVM convention (src/test/)
        for td in test_dirs:
            if td.is_dir():
                test_files.extend(list(td.rglob("*.test.js"))[:10])
                test_files.extend(list(td.rglob("*.spec.js"))[:10])
        jvm_test = repo_path / "src" / "test"
        if jvm_test.is_dir():
            test_files.extend(list(jvm_test.rglob("*.kt"))[:10])
            test_files.extend(list(jvm_test.rglob("*.java"))[:10])

        if not test_files:
            return CheckResult(
                name="tests_named_for_behavior",
                category=_CATEGORY,
                passed=False,
                severity="optional",
                message="No test files found to inspect for naming patterns",
            )

        behavior_count = 0
        for tf in test_files[:20]:
            try:
                text = tf.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if _BEHAVIOR_TEST_RE.search(text):
                behavior_count += 1

        passed = behavior_count > 0
        return CheckResult(
            name="tests_named_for_behavior",
            category=_CATEGORY,
            passed=passed,
            severity="optional",
            message=(
                f"Behaviour-driven naming found in {behavior_count}/{len(test_files[:20])} sampled test files"
                if passed
                else "No behaviour-driven naming detected (test_should_*, test_when_*, it(), describe())"
            ),
            detail=(
                ""
                if passed
                else (
                    "Consider naming tests after the behaviour they verify: "
                    "`test_should_return_404_when_user_not_found` reads like a spec."
                )
            ),
        )

    def _find_ci_files(self, repo_path: Path) -> list[Path]:
        """Return all CI config files found in the repo."""
        files: list[Path] = []
        gha_dir = repo_path / ".github" / "workflows"
        if gha_dir.is_dir():
            files.extend(gha_dir.glob("*.yml"))
            files.extend(gha_dir.glob("*.yaml"))
        gitlab = repo_path / ".gitlab-ci.yml"
        if gitlab.exists():
            files.append(gitlab)
        return files

    def _check_ci_exists(self, ci_files: list[Path]) -> CheckResult:
        if ci_files:
            names = ", ".join(f.name for f in ci_files[:3])
            return CheckResult(
                name="ci_exists",
                category=_CATEGORY,
                passed=True,
                severity="optional",
                message=f"CI config found: {names}",
            )
        return CheckResult(
            name="ci_exists",
            category=_CATEGORY,
            passed=False,
            severity="optional",
            message="No CI configuration found (.github/workflows/ or .gitlab-ci.yml)",
            detail="Add a GitHub Actions workflow or GitLab CI config that runs on every PR.",
        )

    def _check_ci_runs_tests(self, ci_files: list[Path]) -> CheckResult:
        if not ci_files:
            return CheckResult(
                name="ci_runs_tests",
                category=_CATEGORY,
                passed=False,
                severity="optional",
                message="No CI config — cannot check if tests run",
            )

        ci_keywords = re.compile(
            r"(?:pytest|vitest|jest|go test|dotnet test|gradlew test|npm test|yarn test|make test)",
            re.IGNORECASE,
        )
        for wf in ci_files:
            try:
                text = wf.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if ci_keywords.search(text):
                return CheckResult(
                    name="ci_runs_tests",
                    category=_CATEGORY,
                    passed=True,
                    severity="optional",
                    message=f"CI explicitly runs tests (found in {wf.name})",
                )

        return CheckResult(
            name="ci_runs_tests",
            category=_CATEGORY,
            passed=False,
            severity="optional",
            message="CI exists but no explicit test command found",
            detail=(
                "No pytest/vitest/jest/dotnet test/gradlew test command detected. "
                "If tests run via a reusable workflow, this is expected."
            ),
        )
