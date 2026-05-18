"""Language and framework auto-detector.

Detects the primary language/framework of a repo by inspecting files in the
repo root (and a few well-known subdirectories). Returns a dict:

    {"language": "python_django", "detected_by": ["manage.py", "settings.py"]}

The ``language`` value is one of:
    python_django, python_flask, python_fastapi, python,
    typescript_next, typescript_react, typescript,
    nodejs,
    kotlin_spring, kotlin,
    go, dotnet, unknown
"""

from __future__ import annotations

import re
from pathlib import Path


def _has(repo_path: Path, *names: str) -> list[str]:
    """Return the subset of *names* that exist anywhere directly in repo_path."""
    return [n for n in names if (repo_path / n).exists()]


def _requirements_contains(repo_path: Path, package: str) -> bool:
    """Return True if requirements.txt mentions *package* (case-insensitive)."""
    req = repo_path / "requirements.txt"
    if not req.is_file():
        return False
    content = req.read_text(encoding="utf-8", errors="ignore").lower()
    return package.lower() in content


def _detect_python_django(repo_path: Path) -> dict | None:
    markers = _has(repo_path, "manage.py")
    # settings.py may be nested; accept if manage.py exists and settings is
    # found anywhere one level deep.
    settings_found = (
        (repo_path / "settings.py").exists()
        or any(repo_path.glob("*/settings.py"))
        or any(repo_path.glob("*/settings/__init__.py"))
    )
    if markers and settings_found:
        return {"language": "python_django", "detected_by": ["manage.py", "settings.py"]}
    return None


def _detect_python_flask(repo_path: Path) -> dict | None:
    has_req = (repo_path / "requirements.txt").exists()
    app_files = _has(repo_path, "app.py", "wsgi.py")
    if app_files and has_req:
        return {"language": "python_flask", "detected_by": app_files + ["requirements.txt"]}
    return None


def _detect_python_fastapi(repo_path: Path) -> dict | None:
    has_main = (repo_path / "main.py").exists()
    if has_main and _requirements_contains(repo_path, "fastapi"):
        return {"language": "python_fastapi", "detected_by": ["main.py", "requirements.txt"]}
    return None


def _detect_python(repo_path: Path) -> dict | None:
    markers = _has(repo_path, "requirements.txt", "pyproject.toml")
    if markers:
        return {"language": "python", "detected_by": markers}
    return None


def _detect_typescript_next(repo_path: Path) -> dict | None:
    matches = list(repo_path.glob("next.config.*"))
    if matches:
        return {
            "language": "typescript_next",
            "detected_by": [m.name for m in matches],
        }
    return None


def _detect_typescript_react(repo_path: Path) -> dict | None:
    has_pkg = (repo_path / "package.json").exists()
    has_src = (repo_path / "src").is_dir()
    has_tsx = bool(list(repo_path.rglob("*.tsx"))[:1])
    if has_pkg and has_src and has_tsx:
        return {
            "language": "typescript_react",
            "detected_by": ["package.json", "src/", "*.tsx"],
        }
    return None


def _detect_typescript(repo_path: Path) -> dict | None:
    if (repo_path / "tsconfig.json").exists():
        return {"language": "typescript", "detected_by": ["tsconfig.json"]}
    return None


def _detect_nodejs(repo_path: Path) -> dict | None:
    """Catch plain Node.js / JavaScript repos: package.json but no tsconfig."""
    has_pkg = (repo_path / "package.json").exists()
    has_tsconfig = (repo_path / "tsconfig.json").exists()
    if has_pkg and not has_tsconfig:
        return {"language": "nodejs", "detected_by": ["package.json"]}
    return None


def _detect_kotlin_spring(repo_path: Path) -> dict | None:
    has_gradle = (repo_path / "build.gradle.kts").exists()
    has_kotlin_src = (repo_path / "src" / "main" / "kotlin").is_dir()
    if has_gradle and has_kotlin_src:
        return {
            "language": "kotlin_spring",
            "detected_by": ["build.gradle.kts", "src/main/kotlin"],
        }
    return None


def _detect_kotlin(repo_path: Path) -> dict | None:
    """Generic Kotlin: build.gradle.kts or any .kt source files."""
    if (repo_path / "build.gradle.kts").exists():
        return {"language": "kotlin", "detected_by": ["build.gradle.kts"]}
    kt_files = list(repo_path.rglob("*.kt"))[:1]
    if kt_files:
        return {"language": "kotlin", "detected_by": ["*.kt"]}
    return None


def _detect_go(repo_path: Path) -> dict | None:
    if (repo_path / "go.mod").exists():
        return {"language": "go", "detected_by": ["go.mod"]}
    return None


def _detect_dotnet(repo_path: Path) -> dict | None:
    csproj = list(repo_path.glob("**/*.csproj"))
    sln = list(repo_path.glob("*.sln"))
    if csproj or sln:
        markers = [p.name for p in (csproj + sln)[:2]]
        return {"language": "dotnet", "detected_by": markers}
    return None


# Detection order matters — more specific first.
# Non-JS languages that may carry a package.json for tooling (yarn, npm scripts)
# must be checked BEFORE the nodejs/typescript detectors.
_DETECTORS = [
    _detect_python_django,
    _detect_python_fastapi,
    _detect_python_flask,
    _detect_python,
    _detect_dotnet,        # .sln/.csproj repos often also have package.json
    _detect_kotlin_spring,
    _detect_kotlin,        # build.gradle.kts repos may have package.json
    _detect_go,
    _detect_typescript_next,
    _detect_typescript_react,
    _detect_typescript,
    _detect_nodejs,        # package.json without tsconfig = plain Node/JS
]

# Regex used by security check — exported so tests can import it directly.
_FLOATING_VERSION_RE = re.compile(r"^\s*[A-Za-z0-9_\-\[\]]+\s*[^=!<>~\s]")


def detect(repo_path: Path) -> dict:
    """Detect the primary language/framework of the repo at *repo_path*."""
    for detector in _DETECTORS:
        result = detector(repo_path)
        if result is not None:
            return result
    return {"language": "unknown", "detected_by": []}
