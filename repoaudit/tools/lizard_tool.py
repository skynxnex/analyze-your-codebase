"""lizard cyclomatic complexity integration."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class LizardResult:
    ran: bool = False
    error: str = ""
    avg_complexity: float = 0.0
    max_complexity: int = 0
    functions_over_10: int = 0   # CCN > 10 = complex
    functions_over_15: int = 0   # CCN > 15 = very complex
    total_functions: int = 0
    worst_functions: list[dict] = field(default_factory=list)  # [{name, ccn, file}] top 5


def run_lizard(repo_path: Path, timeout: int = 60) -> LizardResult:
    """Run lizard on repo_path and return complexity results."""
    try:
        proc = subprocess.run(
            [
                "lizard", str(repo_path), "--output_file", "/dev/stdout",
                "-l", "python", "-l", "javascript", "-l", "typescript",
                "-l", "kotlin", "-l", "java", "-l", "csharp", "-l", "go",
                "--csv",
                "-x", "*/\\.venv/*", "-x", "*/venv/*", "-x", "*/node_modules/*",
                "-x", "*/build/*", "-x", "*/target/*", "-x", "*/dist/*",
                "-x", "*/.git/*", "-x", "*/migrations/*", "-x", "*/__pycache__/*",
                "-x", "*/site-packages/*",
            ],
            capture_output=True, text=True, timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return LizardResult(ran=False, error=str(e))

    if proc.returncode not in (0, 1):
        return LizardResult(ran=False, error=proc.stderr[:300])

    result = LizardResult(ran=True)
    lines = proc.stdout.strip().splitlines()
    ccn_values: list[int] = []
    worst: list[dict] = []

    for line in lines:
        parts = line.split(",")
        # lizard CSV: NLOC,CCN,token,param,length,location,file,function,long_name
        if len(parts) < 8:
            continue
        try:
            ccn = int(parts[1].strip())
        except ValueError:
            continue
        func_name = parts[7].strip() if len(parts) > 7 else "?"
        file_name = parts[6].strip() if len(parts) > 6 else "?"
        ccn_values.append(ccn)
        if ccn > 10:
            result.functions_over_10 += 1
        if ccn > 15:
            result.functions_over_15 += 1
        if ccn > 10 and len(worst) < 5:
            worst.append({"name": func_name, "ccn": ccn, "file": file_name})

    if ccn_values:
        result.total_functions = len(ccn_values)
        result.avg_complexity = round(sum(ccn_values) / len(ccn_values), 1)
        result.max_complexity = max(ccn_values)
    result.worst_functions = sorted(worst, key=lambda x: x["ccn"], reverse=True)[:5]
    return result
