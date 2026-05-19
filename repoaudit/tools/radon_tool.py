"""radon Python code metrics integration."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RadonResult:
    ran: bool = False
    error: str = ""
    avg_maintainability: float = 0.0   # 0-100, >65 = good
    grade: str = ""                     # A/B/C/D/E/F
    files_graded: int = 0


def run_radon(repo_path: Path, timeout: int = 60) -> RadonResult:
    """Run radon mi (maintainability index) on repo_path."""
    try:
        proc = subprocess.run(
            ["radon", "mi", str(repo_path), "-j"],
            capture_output=True, text=True, timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return RadonResult(ran=False, error=str(e))

    if proc.returncode != 0:
        return RadonResult(ran=False, error=proc.stderr[:300])

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        return RadonResult(ran=False, error=f"JSON parse error: {e}")

    scores: list[float] = []
    for file_data in data.values():
        if isinstance(file_data, dict) and "mi" in file_data:
            scores.append(file_data["mi"])

    if not scores:
        return RadonResult(ran=True, files_graded=0,
                           avg_maintainability=100.0, grade="A")

    avg = sum(scores) / len(scores)
    if avg >= 65:
        grade = "A"
    elif avg >= 55:
        grade = "B"
    elif avg >= 45:
        grade = "C"
    elif avg >= 35:
        grade = "D"
    else:
        grade = "F"

    return RadonResult(
        ran=True,
        avg_maintainability=round(avg, 1),
        grade=grade,
        files_graded=len(scores),
    )
