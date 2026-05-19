"""Fingerprint builder.

Assembles a structured, serialisable snapshot of a repo's properties, check
results, and category scores.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from repoaudit.checks.base import CheckResult

# Weight per severity level.
_WEIGHTS: dict[str, int] = {
    "required": 3,
    "recommended": 1,
    "optional": 0,
}

_CATEGORIES = ("ai_readiness", "security", "devex", "testing")


def _score_category(results: list[CheckResult], category: str) -> float:
    """Return a 0–100 score for *category* based on weighted check results."""
    relevant = [r for r in results if r.category == category]
    total_weight = sum(_WEIGHTS[r.severity] for r in relevant)
    if total_weight == 0:
        return 100.0
    passed_weight = sum(
        _WEIGHTS[r.severity] for r in relevant if r.passed
    )
    return round(passed_weight / total_weight * 100, 1)


def _git_remote_url(repo_path: Path) -> str:
    """Return the git remote origin URL, or empty string if unavailable."""
    try:
        proc = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5, cwd=str(repo_path),
        )
        return proc.stdout.strip() if proc.returncode == 0 else ""
    except Exception:
        return ""


def _git_branch(repo_path: Path) -> str:
    """Return the current git branch name, or empty string."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5, cwd=str(repo_path),
        )
        return proc.stdout.strip() if proc.returncode == 0 else ""
    except Exception:
        return ""


def build(
    repo_path: Path,
    language: dict,
    check_results: list[CheckResult],
) -> dict:
    """Build and return a fingerprint dict for the given repo."""
    scores = {cat: _score_category(check_results, cat) for cat in _CATEGORIES}
    if scores:
        scores["overall"] = round(sum(scores.values()) / len(scores), 1)
    else:
        scores["overall"] = 0.0

    resolved = repo_path.resolve()
    has_git = (repo_path / ".git").exists()
    file_count = sum(1 for _ in repo_path.rglob("*") if _.is_file())

    return {
        "repo_path": str(resolved),
        "repo_name": resolved.name,
        "language": language,
        "check_results": [r.to_dict() for r in check_results],
        "score": scores,
        "file_count": file_count,
        "has_git": has_git,
        "git_remote": _git_remote_url(repo_path) if has_git else "",
        "git_branch": _git_branch(repo_path) if has_git else "",
    }
