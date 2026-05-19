"""pip-audit dependency vulnerability integration."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PipAuditResult:
    ran: bool = False
    error: str = ""
    vulnerable_packages: int = 0
    total_vulnerabilities: int = 0
    critical: int = 0
    high: int = 0
    findings: list[dict] = field(default_factory=list)  # up to 10: {package, version, vuln_id, description}


def run_pip_audit(repo_path: Path, timeout: int = 120) -> PipAuditResult:
    """Run pip-audit on requirements files found in repo_path."""
    # Find requirements files
    req_files = list(repo_path.glob("requirements*.txt")) + list(repo_path.glob("requirements/*.txt"))

    # Also check for pyproject.toml
    has_pyproject = (repo_path / "pyproject.toml").exists()

    if not req_files and not has_pyproject:
        return PipAuditResult(ran=False, error="No requirements files or pyproject.toml found")

    cmd = ["pip-audit", "-f", "json", "--progress-spinner", "off"]
    if req_files:
        for rf in req_files[:3]:  # limit to 3 files
            cmd.extend(["-r", str(rf)])
    else:
        cmd.append("--no-deps")  # audit the current env if no req files

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(repo_path),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return PipAuditResult(ran=False, error=str(e))

    if proc.returncode not in (0, 1):
        return PipAuditResult(ran=False, error=proc.stderr[:300])

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return PipAuditResult(ran=False, error=f"Could not parse pip-audit output: {proc.stdout[:200]}")

    result = PipAuditResult(ran=True)
    dependencies = data.get("dependencies", [])
    for dep in dependencies:
        vulns = dep.get("vulns", [])
        if not vulns:
            continue
        result.vulnerable_packages += 1
        for vuln in vulns:
            result.total_vulnerabilities += 1
            if len(result.findings) < 10:
                result.findings.append({
                    "package": dep.get("name", "?"),
                    "version": dep.get("version", "?"),
                    "vuln_id": vuln.get("id", "?"),
                    "description": vuln.get("description", "")[:120],
                    "fix_versions": vuln.get("fix_versions", []),
                })

    return result
