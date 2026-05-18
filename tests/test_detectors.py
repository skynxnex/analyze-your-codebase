"""Tests for repoaudit.detectors.language."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from repoaudit.detectors.language import detect


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(tmp_path: Path, relative: str, content: str = "") -> None:
    """Create a file (and parent dirs) in tmp_path."""
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Python / Django
# ---------------------------------------------------------------------------

class TestPythonDjango:
    def test_detects_with_manage_and_settings_in_root(self, tmp_path: Path) -> None:
        _write(tmp_path, "manage.py", "#!/usr/bin/env python")
        _write(tmp_path, "settings.py", "DEBUG = True")

        result = detect(tmp_path)

        assert result["language"] == "python_django"
        assert "manage.py" in result["detected_by"]

    def test_detects_with_nested_settings(self, tmp_path: Path) -> None:
        _write(tmp_path, "manage.py")
        _write(tmp_path, "myapp/settings.py", "DEBUG = True")

        result = detect(tmp_path)

        assert result["language"] == "python_django"

    def test_does_not_detect_without_settings(self, tmp_path: Path) -> None:
        _write(tmp_path, "manage.py")
        _write(tmp_path, "requirements.txt", "Django==4.2.0")

        result = detect(tmp_path)

        # Falls through to generic python detection
        assert result["language"] != "python_django"


# ---------------------------------------------------------------------------
# Python / FastAPI
# ---------------------------------------------------------------------------

class TestPythonFastAPI:
    def test_detects_via_main_and_requirements(self, tmp_path: Path) -> None:
        _write(tmp_path, "main.py", "from fastapi import FastAPI")
        _write(tmp_path, "requirements.txt", "fastapi==0.111.0\nuvicorn==0.29.0\n")

        result = detect(tmp_path)

        assert result["language"] == "python_fastapi"

    def test_does_not_detect_without_fastapi_in_requirements(self, tmp_path: Path) -> None:
        _write(tmp_path, "main.py")
        _write(tmp_path, "requirements.txt", "flask==3.0.0\n")

        result = detect(tmp_path)

        assert result["language"] != "python_fastapi"


# ---------------------------------------------------------------------------
# Python / Flask
# ---------------------------------------------------------------------------

class TestPythonFlask:
    def test_detects_via_app_and_requirements(self, tmp_path: Path) -> None:
        _write(tmp_path, "app.py", "from flask import Flask")
        _write(tmp_path, "requirements.txt", "flask==3.0.0\n")

        result = detect(tmp_path)

        assert result["language"] == "python_flask"

    def test_detects_via_wsgi(self, tmp_path: Path) -> None:
        _write(tmp_path, "wsgi.py", "from app import app")
        _write(tmp_path, "requirements.txt", "flask==3.0.0\n")

        result = detect(tmp_path)

        assert result["language"] == "python_flask"


# ---------------------------------------------------------------------------
# Python (generic)
# ---------------------------------------------------------------------------

class TestPythonGeneric:
    def test_detects_via_requirements(self, tmp_path: Path) -> None:
        _write(tmp_path, "requirements.txt", "requests==2.31.0\n")

        result = detect(tmp_path)

        assert result["language"] == "python"

    def test_detects_via_pyproject(self, tmp_path: Path) -> None:
        _write(tmp_path, "pyproject.toml", '[project]\nname = "mylib"\n')

        result = detect(tmp_path)

        assert result["language"] == "python"


# ---------------------------------------------------------------------------
# TypeScript / Next.js
# ---------------------------------------------------------------------------

class TestTypescriptNext:
    def test_detects_via_next_config_js(self, tmp_path: Path) -> None:
        _write(tmp_path, "next.config.js", "module.exports = {}")

        result = detect(tmp_path)

        assert result["language"] == "typescript_next"

    def test_detects_via_next_config_ts(self, tmp_path: Path) -> None:
        _write(tmp_path, "next.config.ts", "export default {}")

        result = detect(tmp_path)

        assert result["language"] == "typescript_next"


# ---------------------------------------------------------------------------
# TypeScript / React
# ---------------------------------------------------------------------------

class TestTypescriptReact:
    def test_detects_via_package_json_and_tsx(self, tmp_path: Path) -> None:
        _write(tmp_path, "package.json", json.dumps({"name": "my-app"}))
        _write(tmp_path, "src/App.tsx", "export default function App() {}")

        result = detect(tmp_path)

        assert result["language"] == "typescript_react"

    def test_does_not_detect_without_tsx(self, tmp_path: Path) -> None:
        _write(tmp_path, "package.json", json.dumps({"name": "my-app"}))
        _write(tmp_path, "src/index.js", "console.log('hi')")
        # No .tsx file, no tsconfig → should not be typescript_react

        result = detect(tmp_path)

        assert result["language"] != "typescript_react"


# ---------------------------------------------------------------------------
# Kotlin / Spring
# ---------------------------------------------------------------------------

class TestKotlinSpring:
    def test_detects_via_gradle_and_src(self, tmp_path: Path) -> None:
        _write(tmp_path, "build.gradle.kts", 'plugins { kotlin("jvm") }')
        _write(tmp_path, "src/main/kotlin/Main.kt", "fun main() {}")

        result = detect(tmp_path)

        assert result["language"] == "kotlin_spring"
        assert "build.gradle.kts" in result["detected_by"]

    def test_does_not_detect_without_kotlin_src(self, tmp_path: Path) -> None:
        _write(tmp_path, "build.gradle.kts", 'plugins { java }')
        # No src/main/kotlin — falls through to generic kotlin

        result = detect(tmp_path)

        assert result["language"] != "kotlin_spring"


# ---------------------------------------------------------------------------
# Node.js
# ---------------------------------------------------------------------------

class TestNodejs:
    def test_detects_plain_nodejs_via_package_json(self, tmp_path: Path) -> None:
        _write(tmp_path, "package.json", '{"name": "my-service"}')

        result = detect(tmp_path)

        assert result["language"] == "nodejs"
        assert "package.json" in result["detected_by"]

    def test_does_not_detect_nodejs_when_tsconfig_present(self, tmp_path: Path) -> None:
        _write(tmp_path, "package.json", '{"name": "my-service"}')
        _write(tmp_path, "tsconfig.json", '{"compilerOptions": {}}')

        result = detect(tmp_path)

        assert result["language"] == "typescript"

    def test_does_not_detect_nodejs_for_next_project(self, tmp_path: Path) -> None:
        _write(tmp_path, "package.json", '{"name": "my-app"}')
        _write(tmp_path, "next.config.js", "module.exports = {}")

        result = detect(tmp_path)

        assert result["language"] == "typescript_next"


# ---------------------------------------------------------------------------
# Kotlin (generic)
# ---------------------------------------------------------------------------

class TestKotlin:
    def test_detects_kotlin_via_gradle_without_src(self, tmp_path: Path) -> None:
        _write(tmp_path, "build.gradle.kts", 'plugins { kotlin("jvm") }')
        # No src/main/kotlin → should fall through to generic kotlin

        result = detect(tmp_path)

        assert result["language"] == "kotlin"
        assert "build.gradle.kts" in result["detected_by"]

    def test_detects_kotlin_via_kt_files(self, tmp_path: Path) -> None:
        _write(tmp_path, "src/Main.kt", "fun main() {}")

        result = detect(tmp_path)

        assert result["language"] == "kotlin"


# ---------------------------------------------------------------------------
# Go
# ---------------------------------------------------------------------------

class TestGo:
    def test_detects_via_go_mod(self, tmp_path: Path) -> None:
        _write(tmp_path, "go.mod", "module example.com/myapp\n\ngo 1.22\n")

        result = detect(tmp_path)

        assert result["language"] == "go"
        assert "go.mod" in result["detected_by"]


# ---------------------------------------------------------------------------
# .NET
# ---------------------------------------------------------------------------

class TestDotnet:
    def test_detects_via_csproj(self, tmp_path: Path) -> None:
        _write(tmp_path, "MyService/MyService.csproj", "<Project Sdk='Microsoft.NET.Sdk'/>")

        result = detect(tmp_path)

        assert result["language"] == "dotnet"

    def test_detects_via_sln(self, tmp_path: Path) -> None:
        _write(tmp_path, "MySolution.sln", "Microsoft Visual Studio Solution File")

        result = detect(tmp_path)

        assert result["language"] == "dotnet"


# ---------------------------------------------------------------------------
# Unknown
# ---------------------------------------------------------------------------

class TestUnknown:
    def test_empty_directory_returns_unknown(self, tmp_path: Path) -> None:
        result = detect(tmp_path)

        assert result["language"] == "unknown"
        assert result["detected_by"] == []

    def test_random_files_return_unknown(self, tmp_path: Path) -> None:
        _write(tmp_path, "notes.txt", "just some text")
        _write(tmp_path, "data.csv", "a,b,c")

        result = detect(tmp_path)

        assert result["language"] == "unknown"
