"""ruff Python linter integration."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RuffResult:
    ran: bool = False
    error: str = ""
    error_count: int = 0
    warning_count: int = 0
    by_code: dict[str, int] = field(default_factory=dict)   # {"E501": 3, ...}
    sample_messages: list[str] = field(default_factory=list)  # up to 5


def run_ruff(repo_path: Path, timeout: int = 60) -> RuffResult:
    """Run ruff check on repo_path and return results."""
    try:
        proc = subprocess.run(
            ["ruff", "check", str(repo_path), "--output-format", "json", "--quiet"],
            capture_output=True, text=True, timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return RuffResult(ran=False, error=str(e))

    # ruff exits 1 when there are lint errors — that's expected
    if proc.returncode not in (0, 1):
        return RuffResult(ran=False, error=proc.stderr[:300])

    try:
        issues = json.loads(proc.stdout) if proc.stdout.strip() else []
    except json.JSONDecodeError as e:
        return RuffResult(ran=False, error=f"JSON parse error: {e}")

    result = RuffResult(ran=True)
    for issue in issues:
        code = issue.get("code", "?")
        result.by_code[code] = result.by_code.get(code, 0) + 1
        # E/F codes = errors, W = warnings
        if code.startswith(("E", "F")):
            result.error_count += 1
        else:
            result.warning_count += 1
        if len(result.sample_messages) < 5:
            loc = issue.get("location", {})
            msg = (
                f"{issue.get('filename', '?')}:{loc.get('row', '?')}: "
                f"[{code}] {issue.get('message', '')}"
            )
            result.sample_messages.append(msg[:120])

    return result
