"""Tests for all repoaudit checks.

Each check is tested with at least one passing and one failing scenario,
using real temp directories rather than mocks.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from repoaudit.checks.ai_readiness import AIReadinessChecks
from repoaudit.checks.devex import DevExChecks
from repoaudit.checks.security import SecurityChecks
from repoaudit.checks.service_security import ServiceSecurityChecks
from repoaudit.checks.testing import TestingChecks

_LANG_PYTHON = {"language": "python", "detected_by": ["requirements.txt"]}
_LANG_DJANGO = {"language": "python_django", "detected_by": ["manage.py"]}
_LANG_TS = {"language": "typescript_react", "detected_by": ["package.json"]}
_LANG_GO = {"language": "go", "detected_by": ["go.mod"]}
_LANG_UNKNOWN = {"language": "unknown", "detected_by": []}


def _write(tmp_path: Path, relative: str, content: str = "") -> None:
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _result(results, name: str):
    """Return the single CheckResult with the given name."""
    matches = [r for r in results if r.name == name]
    assert len(matches) == 1, f"Expected 1 result for {name!r}, got {len(matches)}"
    return matches[0]


# ===========================================================================
# AI Readiness checks
# ===========================================================================

class TestAIReadiness:
    def setup_method(self):
        self.check = AIReadinessChecks()

    def test_claude_md_exists_passes_when_present(self, tmp_path: Path) -> None:
        _write(tmp_path, "CLAUDE.md", "# CLAUDE\n" * 5)
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert _result(results, "claude_md_exists").passed

    def test_claude_md_exists_passes_when_in_dot_claude(self, tmp_path: Path) -> None:
        _write(tmp_path, ".claude/instructions.md", "# Instructions")
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert _result(results, "claude_md_exists").passed

    def test_claude_md_exists_fails_when_absent(self, tmp_path: Path) -> None:
        results = self.check.run(tmp_path, _LANG_PYTHON)
        r = _result(results, "claude_md_exists")
        assert not r.passed
        assert r.severity == "required"

    def test_readme_substantial_passes_with_30_plus_lines(self, tmp_path: Path) -> None:
        content = "\n".join(f"line {i}" for i in range(35))
        _write(tmp_path, "README.md", content)
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert _result(results, "readme_substantial").passed

    def test_readme_substantial_fails_with_short_readme(self, tmp_path: Path) -> None:
        _write(tmp_path, "README.md", "Short.\n")
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert not _result(results, "readme_substantial").passed

    def test_readme_substantial_fails_when_absent(self, tmp_path: Path) -> None:
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert not _result(results, "readme_substantial").passed

    def test_env_vars_documented_passes_with_env_example(self, tmp_path: Path) -> None:
        _write(tmp_path, ".env.example", "DATABASE_URL=\nSECRET_KEY=\n")
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert _result(results, "env_vars_documented").passed

    def test_env_vars_documented_fails_with_dotenv_but_no_example(self, tmp_path: Path) -> None:
        _write(tmp_path, ".env", "DATABASE_URL=postgres://...\n")
        results = self.check.run(tmp_path, _LANG_PYTHON)
        r = _result(results, "env_vars_documented")
        assert not r.passed

    def test_env_vars_documented_passes_when_no_env_at_all(self, tmp_path: Path) -> None:
        # No .env, no example — not applicable, should pass.
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert _result(results, "env_vars_documented").passed

    def test_naming_consistent_passes_when_only_snake_case(self, tmp_path: Path) -> None:
        for name in ("my_module.py", "some_utils.py", "base_class.py"):
            _write(tmp_path, name)
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert _result(results, "naming_consistent").passed

    def test_naming_consistent_fails_with_mixed_conventions(self, tmp_path: Path) -> None:
        _write(tmp_path, "myModule.js")    # camelCase
        _write(tmp_path, "my_utils.py")   # snake_case
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert not _result(results, "naming_consistent").passed

    def test_dependencies_explicit_passes_with_keyword_in_readme(self, tmp_path: Path) -> None:
        content = "\n".join(f"line {i}" for i in range(10))
        content += "\nThis service depends on PostgreSQL and Redis.\n"
        _write(tmp_path, "README.md", content)
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert _result(results, "dependencies_explicit").passed

    def test_dependencies_explicit_fails_without_docs(self, tmp_path: Path) -> None:
        results = self.check.run(tmp_path, _LANG_PYTHON)
        r = _result(results, "dependencies_explicit")
        assert not r.passed
        assert r.severity == "optional"


# ===========================================================================
# Security checks
# ===========================================================================

class TestSecurity:
    def setup_method(self):
        self.check = SecurityChecks()

    def test_no_hardcoded_secrets_passes_clean_file(self, tmp_path: Path) -> None:
        _write(tmp_path, "app.py", "import os\nSECRET = os.environ['SECRET_KEY']\n")
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert _result(results, "no_hardcoded_secrets").passed

    def test_no_hardcoded_secrets_fails_with_literal_password(self, tmp_path: Path) -> None:
        _write(tmp_path, "config.py", "password = 'super-secret-123'\n")
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert not _result(results, "no_hardcoded_secrets").passed

    def test_no_hardcoded_secrets_fails_with_api_key_literal(self, tmp_path: Path) -> None:
        _write(tmp_path, "client.py", "api_key = 'sk-abcdef12345678'\n")
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert not _result(results, "no_hardcoded_secrets").passed

    def test_no_dotenv_committed_passes_no_dotenv(self, tmp_path: Path) -> None:
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert _result(results, "no_dotenv_committed").passed

    def test_no_dotenv_committed_passes_when_gitignored(self, tmp_path: Path) -> None:
        _write(tmp_path, ".env", "SECRET=abc\n")
        _write(tmp_path, ".gitignore", ".env\n")
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert _result(results, "no_dotenv_committed").passed

    def test_no_dotenv_committed_fails_when_not_gitignored(self, tmp_path: Path) -> None:
        _write(tmp_path, ".env", "SECRET=abc\n")
        _write(tmp_path, ".gitignore", "*.pyc\n")  # .env not listed
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert not _result(results, "no_dotenv_committed").passed

    def test_deps_pinned_passes_with_exact_versions(self, tmp_path: Path) -> None:
        _write(tmp_path, "requirements.txt", "click==8.1.8\npyyaml==6.0.2\n")
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert _result(results, "deps_pinned").passed

    def test_deps_pinned_fails_with_unpinned_requirements(self, tmp_path: Path) -> None:
        _write(tmp_path, "requirements.txt", "click\nrequests>=2.0\n")
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert not _result(results, "deps_pinned").passed

    def test_deps_pinned_passes_when_no_requirements(self, tmp_path: Path) -> None:
        # No requirements.txt — cannot audit, should pass (not applicable).
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert _result(results, "deps_pinned").passed

    def test_deps_pinned_typescript_fails_with_caret(self, tmp_path: Path) -> None:
        pkg = {"dependencies": {"react": "^18.2.0"}, "devDependencies": {}}
        _write(tmp_path, "package.json", json.dumps(pkg))
        results = self.check.run(tmp_path, _LANG_TS)
        assert not _result(results, "deps_pinned").passed

    def test_deps_pinned_typescript_passes_with_exact(self, tmp_path: Path) -> None:
        pkg = {"dependencies": {"react": "18.2.0"}, "devDependencies": {}}
        _write(tmp_path, "package.json", json.dumps(pkg))
        results = self.check.run(tmp_path, _LANG_TS)
        assert _result(results, "deps_pinned").passed

    def test_no_latest_docker_passes_with_pinned_image(self, tmp_path: Path) -> None:
        _write(tmp_path, "Dockerfile", "FROM python:3.11-slim\nWORKDIR /app\n")
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert _result(results, "no_latest_docker").passed

    def test_no_latest_docker_fails_with_latest_tag(self, tmp_path: Path) -> None:
        _write(tmp_path, "Dockerfile", "FROM python:latest\nWORKDIR /app\n")
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert not _result(results, "no_latest_docker").passed

    def test_no_latest_docker_fails_in_compose(self, tmp_path: Path) -> None:
        content = "services:\n  app:\n    image: myapp:latest\n"
        _write(tmp_path, "docker-compose.yml", content)
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert not _result(results, "no_latest_docker").passed

    def test_no_latest_docker_passes_when_no_docker_files(self, tmp_path: Path) -> None:
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert _result(results, "no_latest_docker").passed


# ===========================================================================
# New security checks (standalone, not via run())
# ===========================================================================

def test_auth_middleware_found_python(tmp_path: Path) -> None:
    src = tmp_path / "app"
    src.mkdir()
    (src / "middleware.py").write_text(
        "from rest_framework_simplejwt.authentication import JWTAuthentication\n"
    )
    checks = SecurityChecks()
    result = checks._check_auth_middleware(tmp_path, "python")
    assert result.passed is True


def test_auth_middleware_not_found(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("def hello(): return 'world'\n")
    checks = SecurityChecks()
    result = checks._check_auth_middleware(tmp_path, "python")
    assert result.passed is False


def test_cors_wildcard_fails(tmp_path: Path) -> None:
    (tmp_path / "settings.py").write_text("CORS_ALLOW_ALL_ORIGINS = True\n")
    checks = SecurityChecks()
    result = checks._check_cors(tmp_path, "python")
    assert result.passed is False


def test_cors_explicit_passes(tmp_path: Path) -> None:
    (tmp_path / "settings.py").write_text(
        "CORS_ALLOWED_ORIGINS = ['https://example.com']\n"
    )
    checks = SecurityChecks()
    result = checks._check_cors(tmp_path, "python")
    assert result.passed is True


def test_dep_audit_found_in_ci(tmp_path: Path) -> None:
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text("- run: pip-audit\n")
    checks = SecurityChecks()
    result = checks._check_dep_audit_in_ci(tmp_path)
    assert result.passed is True


def test_dep_audit_not_found(tmp_path: Path) -> None:
    checks = SecurityChecks()
    result = checks._check_dep_audit_in_ci(tmp_path)
    assert result.passed is False


def test_https_redirect_found_in_dotnet(tmp_path: Path) -> None:
    (tmp_path / "Program.cs").write_text("app.UseHttpsRedirection();\n")
    checks = SecurityChecks()
    result = checks._check_https_enforcement(tmp_path)
    assert result.passed is True


# ===========================================================================
# Trivy and detect-secrets checks
# ===========================================================================

from unittest.mock import patch, MagicMock


def test_trivy_check_passes_when_trivy_not_installed(tmp_path: Path) -> None:
    with patch("repoaudit.tools.trivy.subprocess.run", side_effect=FileNotFoundError):
        checks = SecurityChecks()
        result = checks._check_trivy(tmp_path)
    assert result.passed is True
    assert "not available" in result.message


def test_trivy_check_fails_on_critical_vulns(tmp_path: Path) -> None:
    trivy_output = json.dumps({
        "Results": [{
            "Vulnerabilities": [{
                "VulnerabilityID": "CVE-2024-1234",
                "PkgName": "requests",
                "Severity": "CRITICAL",
                "Title": "Critical vuln in requests",
            }]
        }]
    })
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stdout = trivy_output
    mock_proc.stderr = ""
    with patch("repoaudit.tools.trivy.subprocess.run", return_value=mock_proc):
        checks = SecurityChecks()
        result = checks._check_trivy(tmp_path)
    assert result.passed is False
    assert "critical" in result.message.lower()


def test_detect_secrets_passes_when_not_installed(tmp_path: Path) -> None:
    with patch("repoaudit.tools.detect_secrets_tool.subprocess.run", side_effect=FileNotFoundError):
        checks = SecurityChecks()
        result = checks._check_detect_secrets(tmp_path)
    assert result.passed is True


def test_detect_secrets_fails_when_secrets_found(tmp_path: Path) -> None:
    ds_output = json.dumps({
        "results": {
            "config.py": [{
                "type": "Secret Keyword",
                "line_number": 42,
            }]
        }
    })
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = ds_output
    mock_proc.stderr = ""
    with patch("repoaudit.tools.detect_secrets_tool.subprocess.run", return_value=mock_proc):
        checks = SecurityChecks()
        result = checks._check_detect_secrets(tmp_path)
    assert result.passed is False
    assert "1" in result.message


# ===========================================================================
# DevEx checks
# ===========================================================================

class TestDevEx:
    def setup_method(self):
        self.check = DevExChecks()

    def test_docker_compose_exists_passes(self, tmp_path: Path) -> None:
        _write(tmp_path, "docker-compose.yml", "services:\n  app:\n    build: .\n")
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert _result(results, "docker_compose_exists").passed

    def test_docker_compose_exists_passes_yaml_extension(self, tmp_path: Path) -> None:
        _write(tmp_path, "docker-compose.yaml", "services:\n  app:\n    build: .\n")
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert _result(results, "docker_compose_exists").passed

    def test_docker_compose_exists_fails_when_absent(self, tmp_path: Path) -> None:
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert not _result(results, "docker_compose_exists").passed

    def test_dockerfile_exists_passes(self, tmp_path: Path) -> None:
        _write(tmp_path, "Dockerfile", "FROM python:3.11-slim\n")
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert _result(results, "dockerfile_exists").passed

    def test_dockerfile_exists_fails_when_absent(self, tmp_path: Path) -> None:
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert not _result(results, "dockerfile_exists").passed

    def test_seed_script_passes_with_seed_py(self, tmp_path: Path) -> None:
        _write(tmp_path, "seed.py", "# seed the db")
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert _result(results, "seed_script_exists").passed

    def test_seed_script_passes_with_package_json_scripts(self, tmp_path: Path) -> None:
        pkg = {"scripts": {"db:seed": "node scripts/seed.js"}}
        _write(tmp_path, "package.json", json.dumps(pkg))
        results = self.check.run(tmp_path, _LANG_TS)
        assert _result(results, "seed_script_exists").passed

    def test_seed_script_passes_when_absent_but_no_database(self, tmp_path: Path) -> None:
        # No database in docker-compose → seed script not required.
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert _result(results, "seed_script_exists").passed

    def test_seed_script_fails_when_absent_but_database_present(self, tmp_path: Path) -> None:
        _write(tmp_path, "docker-compose.yml",
               "services:\n  db:\n    image: postgres:15\n")
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert not _result(results, "seed_script_exists").passed

    def test_has_database_via_migrations_dir(self, tmp_path: Path) -> None:
        (tmp_path / "migrations").mkdir()
        assert self.check._has_database(tmp_path) is True

    def test_has_database_via_flyway_sql(self, tmp_path: Path) -> None:
        (tmp_path / "src" / "main" / "resources" / "db" / "migration").mkdir(parents=True)
        _write(
            tmp_path,
            "src/main/resources/db/migration/V1__init.sql",
            "CREATE TABLE foo (id INT);",
        )
        assert self.check._has_database(tmp_path) is True

    def test_has_database_via_requirements(self, tmp_path: Path) -> None:
        _write(tmp_path, "requirements.txt", "psycopg2==2.9.9\nrequests==2.31.0\n")
        assert self.check._has_database(tmp_path) is True

    def test_has_database_via_env_file(self, tmp_path: Path) -> None:
        _write(tmp_path, ".env.example", "DATABASE_URL=postgres://localhost/mydb\nSECRET_KEY=changeme\n")
        assert self.check._has_database(tmp_path) is True

    def test_has_database_returns_false_when_no_signals(self, tmp_path: Path) -> None:
        _write(tmp_path, "requirements.txt", "requests==2.31.0\nhttpx==0.27.0\n")
        assert self.check._has_database(tmp_path) is False

    def test_has_database_via_spring_application_yml(self, tmp_path: Path) -> None:
        cfg = tmp_path / "src" / "main" / "resources"
        cfg.mkdir(parents=True)
        (cfg / "application.yml").write_text(
            "spring:\n  datasource:\n    url: jdbc:postgresql://localhost/mydb\n"
        )
        assert self.check._has_database(tmp_path) is True

    def test_has_database_via_alembic_ini(self, tmp_path: Path) -> None:
        (tmp_path / "alembic.ini").write_text(
            "[alembic]\nsqlalchemy.url = postgresql://localhost/mydb\n"
        )
        assert self.check._has_database(tmp_path) is True

    def test_has_database_via_rails_database_yml(self, tmp_path: Path) -> None:
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "database.yml").write_text(
            "default: &default\n  adapter: postgresql\n"
        )
        assert self.check._has_database(tmp_path) is True

    def test_has_database_via_prisma_schema(self, tmp_path: Path) -> None:
        (tmp_path / "prisma").mkdir()
        (tmp_path / "prisma" / "schema.prisma").write_text(
            'datasource db {\n  provider = "postgresql"\n  url = env("DATABASE_URL")\n}\n'
        )
        assert self.check._has_database(tmp_path) is True

    def test_has_database_via_appsettings_json(self, tmp_path: Path) -> None:
        data = {"ConnectionStrings": {"Default": "Server=localhost;Database=mydb;"}}
        (tmp_path / "appsettings.json").write_text(json.dumps(data))
        assert self.check._has_database(tmp_path) is True

    def test_local_setup_documented_passes_with_getting_started(self, tmp_path: Path) -> None:
        content = "# My App\n\n## Getting Started\n\nRun `docker compose up`.\n"
        _write(tmp_path, "README.md", content)
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert _result(results, "local_setup_documented").passed

    def test_local_setup_documented_fails_without_setup_section(self, tmp_path: Path) -> None:
        _write(tmp_path, "README.md", "# My App\n\nThis is a service.\n")
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert not _result(results, "local_setup_documented").passed

    def test_makefile_or_yarn_passes_with_makefile(self, tmp_path: Path) -> None:
        _write(tmp_path, "Makefile", "test:\n\tpytest\n")
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert _result(results, "makefile_or_yarn").passed

    def test_makefile_or_yarn_passes_with_package_json_scripts(self, tmp_path: Path) -> None:
        pkg = {"scripts": {"test": "vitest run"}}
        _write(tmp_path, "package.json", json.dumps(pkg))
        results = self.check.run(tmp_path, _LANG_TS)
        assert _result(results, "makefile_or_yarn").passed

    def test_makefile_or_yarn_fails_when_absent(self, tmp_path: Path) -> None:
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert not _result(results, "makefile_or_yarn").passed


# ===========================================================================
# Testing checks
# ===========================================================================

class TestTestingChecks:
    def setup_method(self):
        self.check = TestingChecks()

    def test_tests_exist_passes_with_tests_dir(self, tmp_path: Path) -> None:
        _write(tmp_path, "tests/test_app.py", "def test_foo(): pass")
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert _result(results, "tests_exist").passed

    def test_tests_exist_fails_when_absent(self, tmp_path: Path) -> None:
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert not _result(results, "tests_exist").passed

    def test_test_config_python_passes_with_pyproject(self, tmp_path: Path) -> None:
        content = "[tool.pytest.ini_options]\ntestpaths = [\"tests\"]\n"
        _write(tmp_path, "pyproject.toml", content)
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert _result(results, "test_config_exists").passed

    def test_test_config_python_passes_with_pytest_ini(self, tmp_path: Path) -> None:
        _write(tmp_path, "pytest.ini", "[pytest]\ntestpaths = tests\n")
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert _result(results, "test_config_exists").passed

    def test_test_config_python_fails_when_absent(self, tmp_path: Path) -> None:
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert not _result(results, "test_config_exists").passed

    def test_test_config_typescript_passes_with_vitest(self, tmp_path: Path) -> None:
        _write(tmp_path, "vitest.config.ts", "export default {}")
        results = self.check.run(tmp_path, _LANG_TS)
        assert _result(results, "test_config_exists").passed

    def test_test_config_typescript_fails_without_config(self, tmp_path: Path) -> None:
        results = self.check.run(tmp_path, _LANG_TS)
        assert not _result(results, "test_config_exists").passed

    def test_behavior_naming_passes_when_test_should_used(self, tmp_path: Path) -> None:
        content = (
            "def test_should_return_200_when_valid():\n"
            "    pass\n"
        )
        _write(tmp_path, "tests/test_api.py", content)
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert _result(results, "tests_named_for_behavior").passed

    def test_behavior_naming_fails_when_no_behavior_pattern(self, tmp_path: Path) -> None:
        _write(tmp_path, "tests/test_api.py", "def test_foo():\n    pass\n")
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert not _result(results, "tests_named_for_behavior").passed

    def test_ci_runs_tests_passes_with_github_actions(self, tmp_path: Path) -> None:
        content = (
            "name: CI\non: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest\n"
            "    steps:\n      - run: pytest\n"
        )
        _write(tmp_path, ".github/workflows/ci.yml", content)
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert _result(results, "ci_runs_tests").passed

    def test_ci_runs_tests_passes_with_gitlab_ci(self, tmp_path: Path) -> None:
        content = "test:\n  script:\n    - pytest tests/\n"
        _write(tmp_path, ".gitlab-ci.yml", content)
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert _result(results, "ci_runs_tests").passed

    def test_ci_runs_tests_fails_without_ci(self, tmp_path: Path) -> None:
        results = self.check.run(tmp_path, _LANG_PYTHON)
        assert not _result(results, "ci_runs_tests").passed

    # Coverage configured
    def test_coverage_configured_via_pyproject(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.coverage.run]\nsource = [\"src\"]\n")
        checks = TestingChecks()
        result = checks._check_coverage_configured(tmp_path, "python")
        assert result.passed is True

    def test_coverage_not_configured(self, tmp_path: Path) -> None:
        checks = TestingChecks()
        result = checks._check_coverage_configured(tmp_path, "python")
        assert result.passed is False

    def test_coverage_configured_via_jest_config(self, tmp_path: Path) -> None:
        (tmp_path / "jest.config.js").write_text("module.exports = { coverage: { provider: 'v8' } };\n")
        checks = TestingChecks()
        result = checks._check_coverage_configured(tmp_path, "typescript")
        assert result.passed is True

    # Integration tests
    def test_integration_tests_found_by_dir(self, tmp_path: Path) -> None:
        (tmp_path / "tests" / "integration").mkdir(parents=True)
        checks = TestingChecks()
        result = checks._check_integration_tests(tmp_path)
        assert result.passed is True

    def test_integration_tests_not_found(self, tmp_path: Path) -> None:
        (tmp_path / "tests").mkdir()
        checks = TestingChecks()
        result = checks._check_integration_tests(tmp_path)
        assert result.passed is False

    # Test ratio
    def test_ratio_passes_when_sufficient(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        for i in range(5):
            (src / f"module_{i}.py").write_text("def foo(): pass\n")
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "test_module_0.py").write_text("def test_foo(): pass\n")
        checks = TestingChecks()
        result = checks._check_test_ratio(tmp_path, "python")
        assert result.passed is True

    def test_ratio_fails_when_low(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        for i in range(20):
            (src / f"module_{i}.py").write_text("def foo(): pass\n")
        # no tests
        checks = TestingChecks()
        result = checks._check_test_ratio(tmp_path, "python")
        assert result.passed is False


# ===========================================================================
# ServiceSecurity checks
# ===========================================================================

class TestServiceSecurityChecks:
    def test_exposure_public_via_dockerfile(self, tmp_path: Path) -> None:
        (tmp_path / "Dockerfile").write_text("FROM python:3.11\nEXPOSE 8000\n")
        checks = ServiceSecurityChecks()
        result = checks._check_exposure(tmp_path)
        assert result.passed is True
        assert "public" in result.message.lower()

    def test_exposure_internal_no_signals(self, tmp_path: Path) -> None:
        checks = ServiceSecurityChecks()
        result = checks._check_exposure(tmp_path)
        assert result.passed is True
        assert "internal" in result.message.lower()

    def test_service_auth_outbound_with_auth(self, tmp_path: Path) -> None:
        (tmp_path / "client.py").write_text(
            'response = requests.get(url, headers={"Authorization": f"Bearer {token}"})\n'
        )
        checks = ServiceSecurityChecks()
        result = checks._check_service_to_service_auth(tmp_path, "python")
        assert result.passed is True

    def test_service_auth_outbound_without_auth(self, tmp_path: Path) -> None:
        (tmp_path / "client.py").write_text(
            "response = requests.get(url)\n"
        )
        checks = ServiceSecurityChecks()
        result = checks._check_service_to_service_auth(tmp_path, "python")
        assert result.passed is False

    def test_sensitive_logging_detected(self, tmp_path: Path) -> None:
        (tmp_path / "app.py").write_text(
            'logger.info(f"User password: {password}")\n'
        )
        checks = ServiceSecurityChecks()
        result = checks._check_sensitive_logging(tmp_path)
        assert result.passed is False

    def test_sensitive_logging_clean(self, tmp_path: Path) -> None:
        (tmp_path / "app.py").write_text(
            'logger.info(f"User logged in: {user_id}")\n'
        )
        checks = ServiceSecurityChecks()
        result = checks._check_sensitive_logging(tmp_path)
        assert result.passed is True

    def test_secrets_via_env_detected(self, tmp_path: Path) -> None:
        (tmp_path / "config.py").write_text(
            'SECRET_KEY = os.environ["SECRET_KEY"]\n'
        )
        checks = ServiceSecurityChecks()
        result = checks._check_secrets_via_env_not_code(tmp_path)
        assert result.passed is True


# ===========================================================================
# Comparator tests
# ===========================================================================

class TestComparator:
    def test_testing_patterns_aggregation(self):
        fingerprints = [
            {
                "repo": "repo-a",
                "checks": [
                    {"name": "coverage_configured", "passed": False},
                    {"name": "integration_tests_exist", "passed": True},
                ],
            },
            {
                "repo": "repo-b",
                "checks": [
                    {"name": "coverage_configured", "passed": False},
                    {"name": "integration_tests_exist", "passed": False},
                ],
            },
        ]
        from repoaudit.cross_repo.comparator import compare
        result = compare(fingerprints)
        assert "repo-a" in result["testing_patterns"]["missing_coverage"]
        assert "repo-b" in result["testing_patterns"]["missing_coverage"]
        assert "repo-b" in result["testing_patterns"]["missing_integration_tests"]
        assert "repo-a" not in result["testing_patterns"]["missing_integration_tests"]

    def test_security_patterns_aggregation(self):
        fingerprints = [
            {
                "repo": "svc-1",
                "checks": [
                    {"name": "auth_middleware", "passed": False},
                    {"name": "cors_configured", "passed": False},
                ],
            },
            {
                "repo": "svc-2",
                "checks": [
                    {"name": "auth_middleware", "passed": True},
                    {"name": "cors_configured", "passed": False},
                ],
            },
        ]
        from repoaudit.cross_repo.comparator import compare
        result = compare(fingerprints)
        assert "svc-1" in result["security_patterns"]["missing_auth"]
        assert "svc-2" not in result["security_patterns"]["missing_auth"]
        assert "svc-1" in result["security_patterns"]["wildcard_cors"]
        assert "svc-2" in result["security_patterns"]["wildcard_cors"]
