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

_DB_IMAGES = re.compile(
    r"image:\s*(?:postgres|mysql|mariadb|mongodb|mongo|redis|elasticsearch|mssql|sqlite)",
    re.IGNORECASE,
)

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

    _SKIP_DIRS = frozenset({"build", "target", "dist", ".gradle", "node_modules", ".git"})

    _MIGRATION_DIRS = (
        "migrations",
        "db/migrate",
        "src/main/resources/db/migration",
    )

    _REQUIREMENTS_DB_KEYWORDS = (
        "psycopg2", "psycopg", "pymysql", "mysqlclient", "SQLAlchemy", "sqlalchemy",
        "alembic", "asyncpg", "aiomysql", "motor", "mongoengine", "pymongo",
        "redis", "aioredis",
    )

    _GRADLE_DB_KEYWORDS = (
        "spring-data", "spring-boot-starter-data", "postgresql", "mysql-connector",
        "h2", "r2dbc", "exposed", "ktorm", "flyway", "liquibase",
    )

    _CSPROJ_DB_KEYWORDS = (
        "Npgsql", "MySql.Data", "Microsoft.EntityFrameworkCore", "Dapper",
        "MongoDB.Driver", "StackExchange.Redis",
    )

    _PACKAGE_JSON_DB_KEYS = (
        "pg", "mysql", "mysql2", "mongoose", "mongodb", "redis", "ioredis",
        "sequelize", "typeorm", "prisma", "knex",
    )

    _ENV_DB_PATTERNS = re.compile(
        r"DATABASE_URL|DB_HOST|DB_NAME|POSTGRES_DB|POSTGRES_HOST|MYSQL_HOST"
        r"|MYSQL_DATABASE|MONGO_URI|MONGODB_URI|REDIS_URL",
        re.IGNORECASE,
    )

    _ENV_FILENAMES = (
        ".env", ".env.example", ".env.sample", ".env.local",
        ".env.dev", ".env.development",
    )

    def _has_database(self, repo_path: Path) -> bool:
        """Return True if any of four signals indicate a database dependency."""
        # Signal 1: docker-compose database image
        for name in ("docker-compose.yml", "docker-compose.yaml",
                     "docker-compose.dev.yml", "docker-compose.dev.yaml"):
            dc = repo_path / name
            if dc.exists():
                text = dc.read_text(encoding="utf-8", errors="ignore")
                if _DB_IMAGES.search(text):
                    return True

        # Signal 2: migration directories / SQL files
        if self._db_from_migrations(repo_path):
            return True

        # Signal 3: ORM / DB driver dependencies
        if self._db_from_deps(repo_path):
            return True

        # Signal 4: env files with DB config keys
        if self._db_from_env(repo_path):
            return True

        return False

    def _db_from_migrations(self, repo_path: Path) -> bool:
        """Return True if migration directories or Flyway SQL files are present."""
        for rel_dir in self._MIGRATION_DIRS:
            if (repo_path / rel_dir).is_dir():
                return True

        # db/**/*.sql at repo root
        db_dir = repo_path / "db"
        if db_dir.is_dir():
            for path in db_dir.rglob("*.sql"):
                if not any(part in self._SKIP_DIRS for part in path.parts):
                    return True

        # Flyway versioned migrations: V<num>__<name>.sql at root or one level deep
        flyway_pattern = re.compile(r"V\d+__.*\.sql$")
        for sql_file in repo_path.glob("*.sql"):
            if flyway_pattern.match(sql_file.name):
                return True
        for sql_file in repo_path.glob("*/*.sql"):
            if flyway_pattern.match(sql_file.name):
                return True

        return False

    def _db_from_deps(self, repo_path: Path) -> bool:
        """Return True if any dependency file references a DB-related package."""
        # requirements.txt variants
        req_globs = list(repo_path.glob("requirements*.txt")) + list(
            repo_path.glob("requirements/*.txt")
        )
        for req_file in req_globs:
            try:
                text = req_file.read_text(encoding="utf-8", errors="ignore")
                if any(kw in text for kw in self._REQUIREMENTS_DB_KEYWORDS):
                    return True
            except OSError:
                pass

        # pyproject.toml — search full text for the same keywords
        pyproject = repo_path / "pyproject.toml"
        if pyproject.exists():
            try:
                text = pyproject.read_text(encoding="utf-8", errors="ignore")
                if any(kw in text for kw in self._REQUIREMENTS_DB_KEYWORDS):
                    return True
            except OSError:
                pass

        # build.gradle.kts / build.gradle
        for gradle_name in ("build.gradle.kts", "build.gradle"):
            gradle = repo_path / gradle_name
            if gradle.exists():
                try:
                    text = gradle.read_text(encoding="utf-8", errors="ignore")
                    if any(kw in text for kw in self._GRADLE_DB_KEYWORDS):
                        return True
                except OSError:
                    pass

        # *.csproj — limit to first 5 files
        for csproj in list(repo_path.rglob("*.csproj"))[:5]:
            if any(part in self._SKIP_DIRS for part in csproj.parts):
                continue
            try:
                text = csproj.read_text(encoding="utf-8", errors="ignore")
                if any(kw in text for kw in self._CSPROJ_DB_KEYWORDS):
                    return True
            except OSError:
                pass

        # package.json — check dependency key names
        pkg_json = repo_path / "package.json"
        if pkg_json.exists():
            try:
                data = json.loads(pkg_json.read_text(encoding="utf-8", errors="ignore"))
                deps: dict = {}
                deps.update(data.get("dependencies") or {})
                deps.update(data.get("devDependencies") or {})
                if any(
                    any(kw in dep_key for kw in self._PACKAGE_JSON_DB_KEYS)
                    for dep_key in deps
                ):
                    return True
            except (OSError, json.JSONDecodeError):
                pass

        return False

    def _db_from_env(self, repo_path: Path) -> bool:
        """Return True if any root-level env file contains a DB config key."""
        for filename in self._ENV_FILENAMES:
            env_file = repo_path / filename
            if env_file.exists():
                try:
                    text = env_file.read_text(encoding="utf-8", errors="ignore")
                    if self._ENV_DB_PATTERNS.search(text):
                        return True
                except OSError:
                    pass
        return False

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

        # Only flag missing seed script if the repo has a database.
        if not self._has_database(repo_path):
            return CheckResult(
                name="seed_script_exists",
                category=_CATEGORY,
                passed=True,
                severity="optional",
                message="No database detected — seed script not required",
            )

        return CheckResult(
            name="seed_script_exists",
            category=_CATEGORY,
            passed=False,
            severity="recommended",
            message="No seed script found (database detected)",
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
