"""Security checks.

Covers: hardcoded secrets, committed .env files, unpinned dependencies,
and Docker images using the 'latest' tag.
"""

from __future__ import annotations

import re
from pathlib import Path

from repoaudit.checks.base import Check, CheckResult
from repoaudit.tools.trivy import run_trivy
from repoaudit.tools.detect_secrets_tool import run_detect_secrets

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
        lang = language.get("language", "unknown")
        return [
            self._check_no_hardcoded_secrets(repo_path),
            self._check_no_dotenv_committed(repo_path),
            self._check_deps_pinned(repo_path, language),
            self._check_no_latest_docker(repo_path),
            self._check_auth_middleware(repo_path, lang),
            self._check_cors(repo_path, lang),
            self._check_dep_audit_in_ci(repo_path),
            self._check_https_enforcement(repo_path),
            self._check_trivy(repo_path),
            self._check_detect_secrets(repo_path),
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

    def _check_auth_middleware(self, repo_path: Path, lang: str) -> CheckResult:
        """Check whether authentication patterns exist in source files."""
        patterns_by_lang: dict[str, list[str]] = {
            "python": [
                "jwt", "JWTAuthentication", "IsAuthenticated", "@login_required",
                "@require_auth", "Authorization", "Bearer", "oauth", "authenticate",
            ],
            "kotlin": [
                "@PreAuthorize", "SecurityConfig", "JwtFilter",
                "UsernamePasswordAuthenticationToken",
                "BearerTokenAuthenticationFilter", "oauth2ResourceServer",
                "httpSecurity",
            ],
            "dotnet": [
                "[Authorize]", "JwtBearer", "AddAuthentication",
                "RequireAuthorization", "IAuthenticationHandler",
            ],
            "typescript": [
                "passport", "jwt.verify", "jsonwebtoken", "@UseGuards",
                "AuthGuard", "bearerAuth",
            ],
            "javascript": [
                "passport", "jwt.verify", "jsonwebtoken", "@UseGuards",
                "AuthGuard", "bearerAuth",
            ],
            "go": ["jwt", "middleware", "Authorization", "Bearer", "auth"],
        }

        # Resolve which pattern list to use (partial match on lang string).
        patterns: list[str] = []
        for key, pat_list in patterns_by_lang.items():
            if key in lang:
                patterns = pat_list
                break
        # Fallback: search all patterns if language unknown.
        if not patterns:
            patterns = [p for pats in patterns_by_lang.values() for p in pats]

        extensions_by_lang: dict[str, set[str]] = {
            "python": {".py"},
            "kotlin": {".kt"},
            "dotnet": {".cs"},
            "typescript": {".ts", ".js"},
            "javascript": {".ts", ".js"},
            "go": {".go"},
        }
        scan_exts: set[str] = set()
        for key, exts in extensions_by_lang.items():
            if key in lang:
                scan_exts = exts
                break
        if not scan_exts:
            scan_exts = {".py", ".kt", ".cs", ".ts", ".js", ".go"}

        _skip = _SKIP_DIRS | {"tests", "test", "__tests__", "spec"}
        files_scanned = 0
        for path in repo_path.rglob("*"):
            if path.is_dir():
                continue
            if any(skip in path.parts for skip in _skip):
                continue
            if path.suffix.lower() not in scan_exts:
                continue
            if files_scanned >= 50:
                break
            try:
                text = path.read_bytes()[:8192].decode("utf-8", errors="ignore")
            except OSError:
                continue
            files_scanned += 1
            if any(pat in text for pat in patterns):
                return CheckResult(
                    name="auth_middleware",
                    category=_CATEGORY,
                    passed=True,
                    severity="recommended",
                    message="Auth patterns detected in source code",
                )

        return CheckResult(
            name="auth_middleware",
            category=_CATEGORY,
            passed=False,
            severity="recommended",
            message="No authentication patterns detected",
            detail=(
                "No JWT/OAuth/session auth patterns found. "
                "If this service has public endpoints, add authentication middleware."
            ),
        )

    def _check_cors(self, repo_path: Path, lang: str) -> CheckResult:
        """Check for CORS configuration, flagging wildcard CORS as a failure."""
        cors_patterns = [
            "CORS", "cors", "CorsPolicy", "AllowedOrigins",
            "Access-Control-Allow-Origin", "@CrossOrigin",
        ]
        wildcard_patterns = [
            re.compile(r"CORS_ALLOW_ALL_ORIGINS\s*=\s*True"),
            re.compile(r"Access-Control-Allow-Origin['\"]?\s*[,:]\s*['\"]?\*"),
            re.compile(r"AllowAnyOrigin\(\)"),
            # Catch "*" appearing on same line as cors/CORS/origin keywords.
            re.compile(r"(?:cors|CORS|origin|Origin).*['\"]?\*['\"]?"),
        ]

        _skip = _SKIP_DIRS | {"tests", "test", "__tests__", "spec"}

        source_exts = {".py", ".kt", ".cs", ".ts", ".js", ".go", ".java"}
        config_names = {
            "appsettings.json", "application.yml", "application.properties",
            "settings.py",
        }

        found_cors = False
        found_wildcard = False

        for path in repo_path.rglob("*"):
            if path.is_dir():
                continue
            if any(skip in path.parts for skip in _skip):
                continue
            if path.suffix.lower() not in source_exts and path.name not in config_names:
                continue
            try:
                text = path.read_bytes()[:8192].decode("utf-8", errors="ignore")
            except OSError:
                continue

            has_cors = any(pat in text for pat in cors_patterns)
            if not has_cors:
                continue

            found_cors = True
            if any(wp.search(text) for wp in wildcard_patterns):
                found_wildcard = True
                break

        if found_wildcard:
            return CheckResult(
                name="cors_configured",
                category=_CATEGORY,
                passed=False,
                severity="optional",
                message="Wildcard CORS detected — allows any origin",
                detail="Replace wildcard CORS with an explicit allowlist of trusted origins.",
            )
        if found_cors:
            return CheckResult(
                name="cors_configured",
                category=_CATEGORY,
                passed=True,
                severity="optional",
                message="CORS configuration found",
            )
        return CheckResult(
            name="cors_configured",
            category=_CATEGORY,
            passed=True,
            severity="optional",
            message="No CORS configuration detected (may not be needed for internal APIs)",
        )

    def _check_dep_audit_in_ci(self, repo_path: Path) -> CheckResult:
        """Check whether a dependency vulnerability audit runs in CI."""
        audit_tools = [
            "pip-audit", "safety", "npm audit", "yarn audit",
            "trivy", "snyk", "dependabot", "grype", "osvscanner",
        ]

        # Check dependabot config files first.
        dependabot_paths = [
            repo_path / ".github" / "dependabot.yml",
            repo_path / ".github" / "dependabot.yaml",
        ]
        for dep_path in dependabot_paths:
            if dep_path.exists():
                return CheckResult(
                    name="dep_audit_in_ci",
                    category=_CATEGORY,
                    passed=True,
                    severity="recommended",
                    message="Dependency audit found in CI: dependabot",
                )

        # Search CI workflow files.
        ci_files: list[Path] = []
        github_wf = repo_path / ".github" / "workflows"
        if github_wf.is_dir():
            ci_files.extend(github_wf.glob("*.yml"))
            ci_files.extend(github_wf.glob("*.yaml"))
        gitlab_ci = repo_path / ".gitlab-ci.yml"
        if gitlab_ci.exists():
            ci_files.append(gitlab_ci)

        for ci_file in ci_files:
            try:
                text = ci_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for tool in audit_tools:
                if tool in text:
                    return CheckResult(
                        name="dep_audit_in_ci",
                        category=_CATEGORY,
                        passed=True,
                        severity="recommended",
                        message=f"Dependency audit found in CI: {tool}",
                    )

        return CheckResult(
            name="dep_audit_in_ci",
            category=_CATEGORY,
            passed=False,
            severity="recommended",
            message="No dependency audit in CI",
            detail=(
                "Add pip-audit, npm audit, or trivy to CI to catch "
                "known CVEs in dependencies."
            ),
        )

    def _check_https_enforcement(self, repo_path: Path) -> CheckResult:
        """Check whether HTTPS is enforced at the application or Docker layer."""
        # --- .NET: look for UseHttpsRedirection in C# source files ---
        for cs_file in repo_path.rglob("*.cs"):
            if any(skip in cs_file.parts for skip in _SKIP_DIRS):
                continue
            try:
                text = cs_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "UseHttpsRedirection" in text:
                return CheckResult(
                    name="https_enforced",
                    category=_CATEGORY,
                    passed=True,
                    severity="optional",
                    message="HTTPS enforcement detected",
                )

        # --- Django: check settings.py for SECURE_SSL_REDIRECT ---
        for settings_file in repo_path.rglob("settings.py"):
            if any(skip in settings_file.parts for skip in _SKIP_DIRS):
                continue
            try:
                text = settings_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "SECURE_SSL_REDIRECT = True" in text:
                return CheckResult(
                    name="https_enforced",
                    category=_CATEGORY,
                    passed=True,
                    severity="optional",
                    message="HTTPS enforcement detected",
                )
            if "SECURE_SSL_REDIRECT = False" in text:
                return CheckResult(
                    name="https_enforced",
                    category=_CATEGORY,
                    passed=False,
                    severity="optional",
                    message="Only HTTP detected — no HTTPS redirect or SSL termination found",
                    detail=(
                        "Ensure HTTPS is enforced, either at the load balancer level "
                        "or in application code."
                    ),
                )

        # --- Docker / docker-compose: check for port 80 with no 443/https ---
        docker_files = list(repo_path.glob("Dockerfile*")) + list(
            repo_path.glob("docker-compose*.yml")
        ) + list(repo_path.glob("docker-compose*.yaml"))

        http_only = False
        for df in docker_files:
            try:
                text = df.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            has_80 = bool(
                re.search(r"EXPOSE\s+80\b", text)
                or re.search(r"['\"]?80:", text)
            )
            has_443_or_https = bool(
                re.search(r"443", text) or re.search(r"https", text, re.IGNORECASE)
            )
            if has_80 and not has_443_or_https:
                http_only = True

        if http_only:
            return CheckResult(
                name="https_enforced",
                category=_CATEGORY,
                passed=False,
                severity="optional",
                message="Only HTTP detected — no HTTPS redirect or SSL termination found",
                detail=(
                    "Ensure HTTPS is enforced, either at the load balancer level "
                    "or in application code."
                ),
            )

        return CheckResult(
            name="https_enforced",
            category=_CATEGORY,
            passed=True,
            severity="optional",
            message=(
                "HTTPS posture unclear — likely terminated at load balancer "
                "(acceptable for internal services)"
            ),
        )

    def _check_trivy(self, repo_path: Path) -> CheckResult:
        result = run_trivy(repo_path)
        if not result.ran:
            return CheckResult(
                name="trivy_scan",
                category=_CATEGORY,
                passed=True,
                severity="recommended",
                message="Trivy not available — skipping vulnerability scan",
            )
        total = result.critical + result.high + result.medium + result.low + result.unknown
        if result.critical > 0 or result.high > 0:
            details = []
            for v in result.vuln_details[:5]:
                details.append(f"{v['id']} ({v['pkg']}): {v['title']}")
            detail_str = "\n".join(details) if details else ""
            return CheckResult(
                name="trivy_scan",
                category=_CATEGORY,
                passed=False,
                severity="required",
                message=f"Trivy: {result.critical} critical, {result.high} high, {result.medium} medium vulnerabilities",
                detail=detail_str,
            )
        if result.medium > 0 or result.low > 0:
            return CheckResult(
                name="trivy_scan",
                category=_CATEGORY,
                passed=True,
                severity="recommended",
                message=f"Trivy: {total} vulnerabilities (none critical/high) — {result.medium} medium, {result.low} low",
            )
        return CheckResult(
            name="trivy_scan",
            category=_CATEGORY,
            passed=True,
            severity="recommended",
            message=f"Trivy: no known vulnerabilities found ({total} total scanned)",
        )

    def _check_detect_secrets(self, repo_path: Path) -> CheckResult:
        result = run_detect_secrets(repo_path)
        if not result.ran:
            return CheckResult(
                name="detect_secrets_scan",
                category=_CATEGORY,
                passed=True,
                severity="recommended",
                message="detect-secrets not available — skipping",
            )
        if result.count == 0:
            return CheckResult(
                name="detect_secrets_scan",
                category=_CATEGORY,
                passed=True,
                severity="required",
                message="detect-secrets: no secrets detected",
            )
        type_summary = ", ".join(f"{k}: {v}" for k, v in list(result.by_type.items())[:5])
        files_summary = ", ".join(result.sample_files[:3])
        return CheckResult(
            name="detect_secrets_scan",
            category=_CATEGORY,
            passed=False,
            severity="required",
            message=f"detect-secrets: {result.count} potential secret(s) found",
            detail=f"Types: {type_summary}\nFiles: {files_summary}",
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
