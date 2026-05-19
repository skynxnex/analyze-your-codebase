"""detect-secrets integration."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SecretsResult:
    ran: bool = False
    error: str = ""
    count: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    sample_files: list[str] = field(default_factory=list)  # up to 5 file paths


def run_detect_secrets(repo_path: Path, timeout: int = 60) -> SecretsResult:
    """Run detect-secrets scan on repo_path and return parsed results."""
    try:
        proc = subprocess.run(
            ["detect-secrets", "scan", str(repo_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return SecretsResult(ran=False, error=str(e))

    if proc.returncode != 0:
        return SecretsResult(ran=False, error=proc.stderr[:500])

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        return SecretsResult(ran=False, error=f"JSON parse error: {e}")

    result = SecretsResult(ran=True)
    results = data.get("results", {})
    files_seen: set[str] = set()
    for file_path, findings in results.items():
        for finding in findings:
            result.count += 1
            kind = finding.get("type", "Unknown")
            result.by_type[kind] = result.by_type.get(kind, 0) + 1
            if file_path not in files_seen and len(result.sample_files) < 5:
                result.sample_files.append(file_path)
                files_seen.add(file_path)

    return result
