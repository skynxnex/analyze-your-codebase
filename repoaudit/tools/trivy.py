"""Trivy vulnerability scanner integration."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TrivyResult:
    ran: bool = False
    error: str = ""
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    unknown: int = 0
    vuln_details: list[dict] = field(default_factory=list)  # [{id, pkg, severity, title}]


def run_trivy(repo_path: Path, timeout: int = 120) -> TrivyResult:
    """Run trivy fs scan on repo_path and return parsed results.

    Returns TrivyResult with ran=False if trivy is not installed or fails.
    """
    try:
        proc = subprocess.run(
            [
                "trivy", "fs",
                "--format", "json",
                "--scanners", "vuln,secret",
                "--quiet",
                str(repo_path),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return TrivyResult(ran=False, error=str(e))

    if proc.returncode not in (0, 1):  # 0=no vulns, 1=vulns found, both OK
        return TrivyResult(ran=False, error=proc.stderr[:500])

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        return TrivyResult(ran=False, error=f"JSON parse error: {e}")

    result = TrivyResult(ran=True)
    for item in data.get("Results", []):
        for vuln in item.get("Vulnerabilities", []):
            sev = vuln.get("Severity", "UNKNOWN").upper()
            if sev == "CRITICAL":
                result.critical += 1
            elif sev == "HIGH":
                result.high += 1
            elif sev == "MEDIUM":
                result.medium += 1
            elif sev == "LOW":
                result.low += 1
            else:
                result.unknown += 1
            if sev in ("CRITICAL", "HIGH") and len(result.vuln_details) < 10:
                result.vuln_details.append({
                    "id": vuln.get("VulnerabilityID", ""),
                    "pkg": vuln.get("PkgName", ""),
                    "severity": sev,
                    "title": vuln.get("Title", "")[:80],
                })
        # Also count secrets found by trivy
        for secret in item.get("Secrets", []):
            sev = secret.get("Severity", "HIGH").upper()
            if sev == "CRITICAL":
                result.critical += 1
            elif sev == "HIGH":
                result.high += 1

    return result
