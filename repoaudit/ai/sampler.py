"""File sampler — picks representative source files to send to Claude.

Keeps total sample size under ~6000 tokens by truncating files at 80 lines.
"""

from __future__ import annotations

from pathlib import Path

_ENTRY_POINT_NAMES: list[str] = [
    "manage.py",
    "app.py",
    "main.py",
    "main.kt",
    "main.go",
    "Program.cs",
    "index.ts",
]

_EXCLUDED_DIRS: set[str] = {
    "tests",
    ".venv",
    "node_modules",
    "__pycache__",
    ".git",
    "venv",
    ".tox",
    "dist",
    "build",
    ".mypy_cache",
    ".ruff_cache",
}

_PREFERRED_DIRS: list[str] = ["app", "src"]

_SOURCE_EXTENSIONS: set[str] = {
    ".py",
    ".kt",
    ".go",
    ".cs",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".java",
    ".rb",
    ".rs",
}

_TEST_PATTERNS: list[str] = ["test_*.py", "*_test.py", "*.test.ts", "*.spec.ts", "*.test.js"]

_MAX_LINES = 80
_MAX_SOURCE_FILES = 3


def _is_excluded(path: Path, repo_root: Path) -> bool:
    """Return True if any part of the path relative to repo_root is an excluded dir."""
    try:
        relative = path.relative_to(repo_root)
    except ValueError:
        return False
    return any(part in _EXCLUDED_DIRS for part in relative.parts)


def _read_truncated(path: Path) -> str:
    """Read a file, truncating at _MAX_LINES lines."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    if len(lines) <= _MAX_LINES:
        return "\n".join(lines)
    return "\n".join(lines[:_MAX_LINES]) + "\n... (truncated)"


def _find_entry_point(repo_path: Path) -> dict | None:
    """Find the primary entry point file."""
    for name in _ENTRY_POINT_NAMES:
        candidate = repo_path / name
        if candidate.is_file():
            content = _read_truncated(candidate)
            return {"path": str(candidate.relative_to(repo_path)), "content": content, "role": "entry_point"}
    return None


def _all_source_files(repo_path: Path) -> list[Path]:
    """Return all non-excluded source files, preferred dirs first."""
    preferred: list[Path] = []
    other: list[Path] = []

    for f in repo_path.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix not in _SOURCE_EXTENSIONS:
            continue
        if _is_excluded(f, repo_path):
            continue
        parent_names = {part for part in f.relative_to(repo_path).parts[:-1]}
        if parent_names & set(_PREFERRED_DIRS):
            preferred.append(f)
        else:
            other.append(f)

    return preferred + other


def _find_source_files(repo_path: Path, entry_point_path: str | None) -> list[dict]:
    """Find up to _MAX_SOURCE_FILES source files, excluding the entry point."""
    candidates = _all_source_files(repo_path)
    results: list[dict] = []
    for f in candidates:
        rel = str(f.relative_to(repo_path))
        if rel == entry_point_path:
            continue
        content = _read_truncated(f)
        if not content:
            continue
        results.append({"path": rel, "content": content, "role": "source"})
        if len(results) >= _MAX_SOURCE_FILES:
            break
    return results


def _find_test_file(repo_path: Path) -> dict | None:
    """Find one test file sample."""
    for pattern in _TEST_PATTERNS:
        for f in repo_path.rglob(pattern):
            if not f.is_file():
                continue
            # Must be inside a tests/ directory or match test pattern explicitly.
            content = _read_truncated(f)
            if content:
                return {
                    "path": str(f.relative_to(repo_path)),
                    "content": content,
                    "role": "test",
                }
    return None


def sample(repo_path: Path) -> list[dict]:
    """Return a representative sample of files from *repo_path*.

    Returns:
        List of dicts with keys ``path``, ``content``, and ``role``.
        Role is one of ``"entry_point"``, ``"source"``, or ``"test"``.
        Returns an empty list if no files are found.
    """
    samples: list[dict] = []

    entry = _find_entry_point(repo_path)
    entry_path = entry["path"] if entry else None
    if entry:
        samples.append(entry)

    sources = _find_source_files(repo_path, entry_path)
    samples.extend(sources)

    test = _find_test_file(repo_path)
    if test:
        samples.append(test)

    return samples
