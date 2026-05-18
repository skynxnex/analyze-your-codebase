"""Testing checks.

Language-aware checks for: test directory existence, test config files,
behaviour-driven test naming, and CI that runs tests.
"""

from __future__ import annotations

import re
from pathlib import Path

from repoaudit.checks.base import Check, CheckResult

_CATEGORY = "testing"

# Directories to skip when searching recursively.
_SKIP_DIRS = {
    "build", "target", "dist", "out", "bin", "obj", ".gradle",
    "node_modules", ".venv", "venv", "__pycache__", ".git",
}

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
            self._check_coverage_configured(repo_path, lang),
            self._check_integration_tests(repo_path),
            self._check_test_ratio(repo_path, lang),
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

    def _check_coverage_configured(self, repo_path: Path, lang: str) -> CheckResult:
        """Check that coverage reporting is configured for this repo."""
        # --- Artifact files that prove coverage has been generated ---
        for name in (".coverage", "coverage.xml"):
            if (repo_path / name).exists():
                return CheckResult(
                    name="coverage_configured",
                    category=_CATEGORY,
                    passed=True,
                    severity="recommended",
                    message=f"Coverage configured (artifact found: {name})",
                )
        if (repo_path / "htmlcov").is_dir():
            return CheckResult(
                name="coverage_configured",
                category=_CATEGORY,
                passed=True,
                severity="recommended",
                message="Coverage configured (htmlcov/ directory found)",
            )
        for pattern in ("lcov.info", "clover.xml"):
            matches = [
                p for p in repo_path.rglob(pattern)
                if not any(s in p.parts for s in _SKIP_DIRS)
            ]
            if matches:
                return CheckResult(
                    name="coverage_configured",
                    category=_CATEGORY,
                    passed=True,
                    severity="recommended",
                    message=f"Coverage configured (artifact found: {matches[0].name})",
                )

        # --- Config-file signals ---
        pyproject = repo_path / "pyproject.toml"
        if pyproject.exists():
            text = pyproject.read_text(encoding="utf-8", errors="ignore")
            if "[tool.coverage" in text:
                return CheckResult(
                    name="coverage_configured",
                    category=_CATEGORY,
                    passed=True,
                    severity="recommended",
                    message="Coverage configured via pyproject.toml",
                )

        setup_cfg = repo_path / "setup.cfg"
        if setup_cfg.exists():
            text = setup_cfg.read_text(encoding="utf-8", errors="ignore")
            if "[coverage:" in text:
                return CheckResult(
                    name="coverage_configured",
                    category=_CATEGORY,
                    passed=True,
                    severity="recommended",
                    message="Coverage configured via setup.cfg",
                )

        pytest_ini = repo_path / "pytest.ini"
        if pytest_ini.exists():
            text = pytest_ini.read_text(encoding="utf-8", errors="ignore")
            if "[pytest]" in text and "--cov" in text:
                return CheckResult(
                    name="coverage_configured",
                    category=_CATEGORY,
                    passed=True,
                    severity="recommended",
                    message="Coverage configured via pytest.ini (--cov in addopts)",
                )

        for pattern in ("jest.config.*", "vitest.config.*"):
            for cfg_file in repo_path.glob(pattern):
                try:
                    text = cfg_file.read_text(encoding="utf-8", errors="ignore")[:4096]
                except OSError:
                    continue
                if "coverage" in text:
                    return CheckResult(
                        name="coverage_configured",
                        category=_CATEGORY,
                        passed=True,
                        severity="recommended",
                        message=f"Coverage configured via {cfg_file.name}",
                    )

        for pattern in ("build.gradle.kts", "build.gradle"):
            gradle = repo_path / pattern
            if gradle.exists():
                text = gradle.read_text(encoding="utf-8", errors="ignore")
                if "jacoco" in text or "kover" in text:
                    return CheckResult(
                        name="coverage_configured",
                        category=_CATEGORY,
                        passed=True,
                        severity="recommended",
                        message=f"Coverage configured via {pattern} (jacoco/kover)",
                    )

        for csproj in repo_path.rglob("*.csproj"):
            if any(s in csproj.parts for s in _SKIP_DIRS):
                continue
            try:
                text = csproj.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "coverlet" in text:
                return CheckResult(
                    name="coverage_configured",
                    category=_CATEGORY,
                    passed=True,
                    severity="recommended",
                    message=f"Coverage configured via {csproj.name} (coverlet)",
                )

        ci_files: list[Path] = []
        gha_dir = repo_path / ".github" / "workflows"
        if gha_dir.is_dir():
            ci_files.extend(gha_dir.glob("*.yml"))
            ci_files.extend(gha_dir.glob("*.yaml"))
        gitlab = repo_path / ".gitlab-ci.yml"
        if gitlab.exists():
            ci_files.append(gitlab)
        for ci_file in ci_files:
            try:
                text = ci_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "coverage" in text or "--cov" in text:
                return CheckResult(
                    name="coverage_configured",
                    category=_CATEGORY,
                    passed=True,
                    severity="recommended",
                    message=f"Coverage configured in CI ({ci_file.name})",
                )

        return CheckResult(
            name="coverage_configured",
            category=_CATEGORY,
            passed=False,
            severity="recommended",
            message="No coverage configuration found",
            detail=(
                "Add coverage reporting (e.g. pytest-cov, jacoco, coverlet) "
                "to track test completeness."
            ),
        )

    def _check_integration_tests(self, repo_path: Path) -> CheckResult:
        """Check for the presence of integration or e2e tests."""
        integration_dir_names = {
            "integration", "integration_tests", "e2e", "e2e_tests",
            "contract", "functional",
        }

        # Check root-level directories.
        for d in repo_path.iterdir():
            if d.is_dir() and d.name.lower() in integration_dir_names:
                return CheckResult(
                    name="integration_tests_exist",
                    category=_CATEGORY,
                    passed=True,
                    severity="optional",
                    message=f"Integration/e2e tests found: {d.name}/",
                )

        # Check under tests/ and test/.
        for parent_name in ("tests", "test"):
            parent = repo_path / parent_name
            if parent.is_dir():
                for d in parent.iterdir():
                    if d.is_dir() and d.name.lower() in integration_dir_names:
                        return CheckResult(
                            name="integration_tests_exist",
                            category=_CATEGORY,
                            passed=True,
                            severity="optional",
                            message=f"Integration/e2e tests found: {parent_name}/{d.name}/",
                        )

        # Check for integration/e2e test files by name pattern.
        integration_file_re = re.compile(
            r"(?:integration|e2e)",
            re.IGNORECASE,
        )
        extensions = (".py", ".ts", ".kt", ".cs")
        for p in repo_path.rglob("*"):
            if any(s in p.parts for s in _SKIP_DIRS):
                continue
            if not p.is_file():
                continue
            if p.suffix not in extensions:
                continue
            # Match by filename containing integration/e2e.
            if integration_file_re.search(p.stem):
                rel = p.relative_to(repo_path)
                return CheckResult(
                    name="integration_tests_exist",
                    category=_CATEGORY,
                    passed=True,
                    severity="optional",
                    message=f"Integration/e2e tests found: {rel}",
                )
            # Match by path segment.
            parts_lower = [part.lower() for part in p.parts]
            if "integration" in parts_lower or "e2e" in parts_lower:
                rel = p.relative_to(repo_path)
                return CheckResult(
                    name="integration_tests_exist",
                    category=_CATEGORY,
                    passed=True,
                    severity="optional",
                    message=f"Integration/e2e tests found: {rel}",
                )

        return CheckResult(
            name="integration_tests_exist",
            category=_CATEGORY,
            passed=False,
            severity="optional",
            message="No integration or e2e tests detected",
            detail=(
                "Consider adding integration tests that verify behaviour "
                "across service boundaries."
            ),
        )

    def _check_test_ratio(self, repo_path: Path, lang: str) -> CheckResult:
        """Check that the test-to-source file ratio is at least 1:10."""
        _skip = _SKIP_DIRS | {"tests", "test", "migrations", "__pycache__"}

        def _rglob_skip(root: Path, pattern: str, extra_skip: set[str] | None = None) -> list[Path]:
            skip = _skip | (extra_skip or set())
            return [
                p for p in root.rglob(pattern)
                if p.is_file() and not any(s in p.parts for s in skip)
            ]

        # --- Source file counting ---
        if "python" in lang:
            src_root = repo_path / "src"
            if src_root.is_dir():
                source_files = _rglob_skip(src_root, "*.py")
            else:
                source_files = _rglob_skip(repo_path, "*.py", {"tests", "test", "migrations"})
        elif lang in ("typescript", "typescript_react", "typescript_next"):
            src_root = repo_path / "src"
            if src_root.is_dir():
                source_files = [
                    p for p in _rglob_skip(src_root, "*.ts") + _rglob_skip(src_root, "*.tsx")
                    if ".test." not in p.name and ".spec." not in p.name
                ]
            else:
                source_files = []
        elif lang in ("kotlin", "kotlin_spring"):
            src_main = repo_path / "src" / "main"
            source_files = _rglob_skip(src_main, "*.kt") if src_main.is_dir() else []
        elif lang == "dotnet":
            src_root = repo_path / "src"
            if src_root.is_dir():
                source_files = [
                    p for p in _rglob_skip(src_root, "*.cs")
                    if "Tests" not in p.parts and "Test" not in p.parent.name
                ]
            else:
                source_files = []
        elif lang == "go":
            source_files = [
                p for p in _rglob_skip(repo_path, "*.go")
                if not p.name.endswith("_test.go")
            ]
        elif lang == "nodejs":
            src_root = repo_path / "src"
            if src_root.is_dir():
                source_files = [
                    p for p in _rglob_skip(src_root, "*.js")
                    if ".test." not in p.name and ".spec." not in p.name
                ]
            else:
                source_files = []
        else:
            return CheckResult(
                name="test_ratio",
                category=_CATEGORY,
                passed=True,
                severity="optional",
                message="Language not recognised — skipping ratio check",
            )

        if len(source_files) < 3:
            return CheckResult(
                name="test_ratio",
                category=_CATEGORY,
                passed=True,
                severity="optional",
                message="Too few source files to compute ratio",
            )

        # --- Test file counting (mirrors _check_tests_exist patterns) ---
        test_patterns: list[tuple[Path, str]] = []
        if "python" in lang:
            for td in (repo_path / "tests", repo_path / "test"):
                if td.is_dir():
                    test_patterns.append((td, "test_*.py"))
        elif lang in ("typescript", "typescript_react", "typescript_next"):
            for pattern in ("*.test.ts", "*.spec.ts", "*.test.tsx", "*.spec.tsx"):
                test_patterns.append((repo_path, pattern))
        elif lang in ("kotlin", "kotlin_spring"):
            src_test = repo_path / "src" / "test"
            if src_test.is_dir():
                test_patterns.append((src_test, "*.kt"))
        elif lang == "dotnet":
            # Collect .cs files from directories whose name contains Test.
            test_files_direct = [
                p for p in repo_path.rglob("*.cs")
                if not any(s in p.parts for s in _SKIP_DIRS)
                and ("Tests" in p.parts or "Test" in p.parent.name)
            ]
            source_count = len(source_files)
            test_count = len(test_files_direct)
            ratio = test_count / source_count
            passed = ratio >= 0.1
            return CheckResult(
                name="test_ratio",
                category=_CATEGORY,
                passed=passed,
                severity="optional",
                message=f"Test/source ratio: {test_count}/{source_count} ({ratio:.0%})",
                detail=(
                    ""
                    if passed
                    else (
                        "Low test coverage signal: fewer than 1 test file per 10 source files. "
                        "Consider adding more tests."
                    )
                ),
            )
        elif lang == "go":
            test_patterns.append((repo_path, "*_test.go"))
        elif lang == "nodejs":
            for td in (repo_path / "tests", repo_path / "test"):
                if td.is_dir():
                    test_patterns.append((td, "*.test.js"))
                    test_patterns.append((td, "*.spec.js"))

        test_files: list[Path] = []
        for root, pattern in test_patterns:
            test_files.extend([
                p for p in root.rglob(pattern)
                if p.is_file() and not any(s in p.parts for s in _SKIP_DIRS)
            ])

        source_count = len(source_files)
        test_count = len(test_files)
        ratio = test_count / source_count
        passed = ratio >= 0.1
        return CheckResult(
            name="test_ratio",
            category=_CATEGORY,
            passed=passed,
            severity="optional",
            message=f"Test/source ratio: {test_count}/{source_count} ({ratio:.0%})",
            detail=(
                ""
                if passed
                else (
                    "Low test coverage signal: fewer than 1 test file per 10 source files. "
                    "Consider adding more tests."
                )
            ),
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
