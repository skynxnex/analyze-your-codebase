"""Inter-service and deployment security checks."""

from __future__ import annotations

import re
from pathlib import Path

from repoaudit.checks.base import Check, CheckResult

_CATEGORY = "service_security"
_SKIP_DIRS = {
    "build", "target", "dist", "out", "bin", "obj", ".gradle",
    "node_modules", ".venv", "venv", "__pycache__", ".git",
}

_OUTBOUND_HTTP_PATTERNS = [
    "requests.get", "requests.post", "httpx.", "RestTemplate",
    "WebClient", "HttpClient", "fetch(", "axios.", "http.NewRequest", "urllib",
]

_AUTH_PATTERNS = [
    "Authorization", "Bearer", "api_key", "API_KEY", "X-API-Key",
    "service_token", "SERVICE_TOKEN", "client_credentials",
]

_SENSITIVE_LOG_RE = re.compile(
    r"(?:log|logger|logging|print|console\.log).*"
    r"(?:password|passwd|secret|token|api_key|credit_card|ssn|cvv|private_key)",
    re.IGNORECASE,
)

_LOG_SOURCE_EXTENSIONS = {".py", ".kt", ".cs", ".ts", ".js", ".go"}

_ENV_VAR_PATTERNS = [
    "os.environ", "os.getenv", "env(", "process.env.",
    "Environment.GetEnvironmentVariable", "System.getenv",
]


class ServiceSecurityChecks(Check):
    """Inter-service and deployment security checks."""

    def run(self, repo_path: Path, language: dict) -> list[CheckResult]:
        lang = language.get("language", "unknown")
        return [
            self._check_exposure(repo_path),
            self._check_service_to_service_auth(repo_path, lang),
            self._check_sensitive_logging(repo_path),
            self._check_secrets_via_env_not_code(repo_path),
        ]

    def _check_exposure(self, repo_path: Path) -> CheckResult:
        """Determine if this service is publicly exposed or internal-only."""
        is_public = False

        # Check paas-*.yaml, adin-*.yml, *ingress*.yaml for host: or ingress
        for pattern in ("paas-*.yaml", "adin-*.yml", "*ingress*.yaml"):
            for f in repo_path.glob(pattern):
                try:
                    text = f.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if "host:" in text or "ingress" in text.lower():
                    is_public = True
                    break
            if is_public:
                break

        if not is_public:
            # Check docker-compose for host-mapped ports (value contains colon)
            for compose_name in ("docker-compose.yml", "docker-compose.yaml"):
                compose = repo_path / compose_name
                if not compose.exists():
                    continue
                try:
                    text = compose.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                in_ports = False
                for line in text.splitlines():
                    stripped = line.strip()
                    if stripped == "ports:":
                        in_ports = True
                        continue
                    if in_ports:
                        if stripped.startswith("-"):
                            value = stripped.lstrip("- \"'").rstrip("\"'")
                            if ":" in value:
                                is_public = True
                                break
                        elif stripped and not stripped.startswith("#"):
                            in_ports = False
                if is_public:
                    break

        if not is_public:
            # Check Dockerfile for EXPOSE directive
            dockerfile = repo_path / "Dockerfile"
            if dockerfile.exists():
                try:
                    text = dockerfile.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    text = ""
                if re.search(r"^EXPOSE\s+\d+", text, re.MULTILINE):
                    is_public = True

        if is_public:
            return CheckResult(
                name="service_exposure",
                category=_CATEGORY,
                passed=True,
                severity="optional",
                message=(
                    "Service appears publicly exposed "
                    "(ingress/port mapping detected)"
                ),
                detail=(
                    "Public services require stricter auth, rate limiting, "
                    "and security headers."
                ),
            )
        return CheckResult(
            name="service_exposure",
            category=_CATEGORY,
            passed=True,
            severity="optional",
            message="Service appears internal-only (no public ingress detected)",
            detail=(
                "Internal services have lower exposure risk but should still "
                "authenticate service-to-service calls."
            ),
        )

    def _check_service_to_service_auth(
        self, repo_path: Path, lang: str
    ) -> CheckResult:
        """Check whether outbound HTTP calls are authenticated."""
        found_outbound = False
        found_auth = False

        files_scanned = 0
        for path in repo_path.rglob("*"):
            if path.is_dir():
                continue
            if any(skip in path.parts for skip in _SKIP_DIRS):
                continue
            if path.suffix.lower() not in {
                ".py", ".kt", ".cs", ".ts", ".js", ".go", ".java",
            }:
                continue
            if files_scanned >= 60:
                break
            try:
                text = path.read_bytes()[:8192].decode("utf-8", errors="ignore")
            except OSError:
                continue
            files_scanned += 1

            if any(pat in text for pat in _OUTBOUND_HTTP_PATTERNS):
                found_outbound = True
            if any(pat in text for pat in _AUTH_PATTERNS):
                found_auth = True

            # Also check scripts for 1Password / docker-secrets patterns
            if "op get" in text or "_FILE" in text:
                found_auth = True

        # Check docker-compose for Docker secrets
        for compose_name in ("docker-compose.yml", "docker-compose.yaml"):
            compose = repo_path / compose_name
            if compose.exists():
                try:
                    text = compose.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    text = ""
                if "secrets:" in text:
                    found_auth = True

        if not found_outbound:
            return CheckResult(
                name="service_auth",
                category=_CATEGORY,
                passed=True,
                severity="recommended",
                message="No outbound HTTP calls detected",
            )
        if found_auth:
            return CheckResult(
                name="service_auth",
                category=_CATEGORY,
                passed=True,
                severity="recommended",
                message="Outbound HTTP calls appear authenticated",
            )
        return CheckResult(
            name="service_auth",
            category=_CATEGORY,
            passed=False,
            severity="recommended",
            message="Outbound HTTP calls detected without apparent authentication",
            detail=(
                "Ensure service-to-service calls include authentication headers "
                "(Bearer token, API key, or mTLS)."
            ),
        )

    def _check_sensitive_logging(self, repo_path: Path) -> CheckResult:
        """Check for log statements that include sensitive field names."""
        match_count = 0
        files_scanned = 0

        for path in repo_path.rglob("*"):
            if path.is_dir():
                continue
            if any(skip in path.parts for skip in _SKIP_DIRS):
                continue
            if path.suffix.lower() not in _LOG_SOURCE_EXTENSIONS:
                continue
            if files_scanned >= 100:
                break
            try:
                text = path.read_bytes()[:8192].decode("utf-8", errors="ignore")
            except OSError:
                continue
            files_scanned += 1

            for line in text.splitlines():
                if _SENSITIVE_LOG_RE.search(line):
                    match_count += 1

        if match_count:
            return CheckResult(
                name="no_sensitive_logging",
                category=_CATEGORY,
                passed=False,
                severity="recommended",
                message=(
                    f"Potential sensitive data in log statements "
                    f"({match_count} occurrence(s) found)"
                ),
                detail=(
                    "Review log statements to ensure passwords, tokens, and secrets "
                    "are not logged. Use redaction or structured logging with field "
                    "filtering."
                ),
            )
        return CheckResult(
            name="no_sensitive_logging",
            category=_CATEGORY,
            passed=True,
            severity="recommended",
            message="No sensitive field names detected in log statements",
        )

    def _check_secrets_via_env_not_code(self, repo_path: Path) -> CheckResult:
        """Check that secrets are loaded from environment variables."""
        found_env_loading = False
        files_scanned = 0
        has_source_files = False

        for path in repo_path.rglob("*"):
            if path.is_dir():
                continue
            if any(skip in path.parts for skip in _SKIP_DIRS):
                continue
            if path.suffix.lower() not in {
                ".py", ".kt", ".cs", ".ts", ".js", ".go", ".java",
            }:
                continue
            if files_scanned >= 60:
                break
            try:
                text = path.read_bytes()[:8192].decode("utf-8", errors="ignore")
            except OSError:
                continue
            files_scanned += 1
            has_source_files = True

            if any(pat in text for pat in _ENV_VAR_PATTERNS):
                found_env_loading = True
                break

        if not has_source_files:
            return CheckResult(
                name="secrets_via_env",
                category=_CATEGORY,
                passed=True,
                severity="recommended",
                message="No source files to inspect",
            )
        if found_env_loading:
            return CheckResult(
                name="secrets_via_env",
                category=_CATEGORY,
                passed=True,
                severity="recommended",
                message="Secrets loaded via environment variables",
            )
        return CheckResult(
            name="secrets_via_env",
            category=_CATEGORY,
            passed=False,
            severity="recommended",
            message="No environment variable secret loading detected",
            detail=(
                "Load secrets via os.environ / process.env / "
                "Environment.GetEnvironmentVariable rather than hardcoding them."
            ),
        )
