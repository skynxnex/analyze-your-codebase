"""interrogate Python docstring coverage integration."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class InterrogateResult:
    ran: bool = False
    error: str = ""
    coverage: float = 0.0      # 0.0–100.0
    missing: int = 0           # functions/classes without docstrings
    total: int = 0


def run_interrogate(repo_path: Path, timeout: int = 60) -> InterrogateResult:
    """Run interrogate on repo_path and return docstring coverage."""
    try:
        proc = subprocess.run(
            [
                "interrogate",
                str(repo_path),
                "--quiet",
                "--ignore-init-method",
                "--ignore-magic",
                "--ignore-private",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return InterrogateResult(ran=False, error=str(e))

    # interrogate exits 1 when coverage < threshold (default 80%) — expected
    if proc.returncode not in (0, 1):
        return InterrogateResult(ran=False, error=proc.stderr[:300])

    # Parse output: "RESULT: PASSED (minimum: 80.0%, actual: 95.3%)"
    # or:           "RESULT: FAILED (minimum: 80.0%, actual: 42.1%)"
    # also:         "actual: 95.3% (57/60)"
    output = proc.stdout + proc.stderr
    coverage_match = re.search(r"actual:\s*([\d.]+)%", output)
    fraction_match = re.search(r"\((\d+)/(\d+)\)", output)

    if not coverage_match:
        return InterrogateResult(ran=False, error=f"Could not parse interrogate output: {output[:200]}")

    coverage = float(coverage_match.group(1))
    total = int(fraction_match.group(2)) if fraction_match else 0
    documented = int(fraction_match.group(1)) if fraction_match else 0
    missing = total - documented

    return InterrogateResult(
        ran=True,
        coverage=coverage,
        missing=missing,
        total=total,
    )
