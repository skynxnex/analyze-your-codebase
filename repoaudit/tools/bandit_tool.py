"""Bandit Python security linter integration."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class BanditResult:
    ran: bool = False
    error: str = ""
    high_severity: int = 0
    medium_severity: int = 0
    low_severity: int = 0
    issues: list[dict] = field(default_factory=list)  # up to 10: {severity, confidence, test_id, text, file, line}


def run_bandit(repo_path: Path, timeout: int = 90) -> BanditResult:
    """Run bandit security scan on repo_path."""
    try:
        proc = subprocess.run(
            [
                "bandit",
                "-r", str(repo_path),
                "-f", "json",
                "--quiet",
                "--exclude", ".venv,venv,build,dist,target,.git,node_modules,migrations",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return BanditResult(ran=False, error=str(e))

    # bandit exits 1 when issues found — expected
    if proc.returncode not in (0, 1):
        return BanditResult(ran=False, error=proc.stderr[:300])

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return BanditResult(ran=False, error=f"Could not parse bandit output: {proc.stdout[:200]}")

    result = BanditResult(ran=True)
    for issue in data.get("results", []):
        sev = issue.get("issue_severity", "").upper()
        if sev == "HIGH":
            result.high_severity += 1
        elif sev == "MEDIUM":
            result.medium_severity += 1
        else:
            result.low_severity += 1

        if len(result.issues) < 10:
            result.issues.append({
                "severity": sev,
                "confidence": issue.get("issue_confidence", ""),
                "test_id": issue.get("test_id", ""),
                "text": issue.get("issue_text", "")[:100],
                "file": issue.get("filename", ""),
                "line": issue.get("line_number", 0),
            })

    return result
