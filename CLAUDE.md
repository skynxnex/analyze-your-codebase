# CLAUDE.md — repoaudit

repoaudit is a language-agnostic CLI that audits codebases for AI-readiness,
security hygiene, developer experience, and test quality. It produces structured
JSON fingerprints and human-readable Markdown reports. No external API calls in
Phase 1.

## Entry point

`repoaudit/cli.py` — Click CLI with two commands: `analyze` and `fingerprint`.

## Key design decisions

**Why fingerprints?**
A fingerprint is a serialisable, version-trackable snapshot of a repo's
properties and check results. It lets you compare repos over time, feed the data
into a future LLM integration (Phase 2), and build dashboards without re-running
the tool.

**Why language-aware checks?**
Test config files differ across ecosystems (`pytest.ini` vs `vitest.config.ts`
vs `jest.config.js`). A single generic check would produce false positives.
Language detection runs first; checks receive the detected language and can
branch accordingly.

**Why no config required?**
The goal is zero-friction adoption: `docker run ... analyze /repo` should give
useful output for any repo. Config only extends defaults — it is never required.

**Scoring weights: required=3, recommended=1, optional=0**
Optional checks surface information without penalising repos that don't need
them. Required/recommended weights reflect urgency, not binary pass/fail.

## Architecture

```
cli.py
  ├── analyze command
  │     ├── detectors/language.py   → detect language
  │     ├── checks/                 → run all checks → list[CheckResult]
  │     ├── fingerprint.py          → build fingerprint dict (includes scores)
  │     └── reporters/markdown.py   → render Markdown from fingerprint
  └── fingerprint command
        ├── detectors/language.py
        ├── checks/
        └── fingerprint.py          → print JSON
```

## Module responsibilities

| Module | Responsibility |
|---|---|
| `repoaudit/cli.py` | Click commands, wiring, output |
| `repoaudit/detectors/language.py` | File-inspection-based language detection |
| `repoaudit/checks/base.py` | `CheckResult` dataclass + `Check` abstract base class |
| `repoaudit/checks/ai_readiness.py` | AI / LLM-readiness checks |
| `repoaudit/checks/security.py` | Secret leakage, dep pinning, Docker tags |
| `repoaudit/checks/devex.py` | Docker, seed script, local dev docs |
| `repoaudit/checks/testing.py` | Test directory, config, naming, CI |
| `repoaudit/checks/__init__.py` | `ALL_CHECKS` list — single registration point |
| `repoaudit/fingerprint.py` | Assembles fingerprint dict + scores |
| `repoaudit/reporters/markdown.py` | Renders Markdown from fingerprint |

## How to add a new check

```python
# repoaudit/checks/my_category.py
from pathlib import Path
from repoaudit.checks.base import Check, CheckResult


class MyNewCheck(Check):
    def run(self, repo_path: Path, language: dict) -> list[CheckResult]:
        passed = (repo_path / "some-file").exists()
        return [
            CheckResult(
                name="some_file_exists",
                category="my_category",
                passed=passed,
                severity="recommended",
                message="some-file found" if passed else "some-file missing",
                detail="Add some-file to improve X.",
            )
        ]
```

Then register it in `repoaudit/checks/__init__.py`:

```python
from repoaudit.checks.my_category import MyNewCheck

ALL_CHECKS: list[type[Check]] = [
    ...,
    MyNewCheck,
]
```

## How to add a new language detector

Edit `repoaudit/detectors/language.py`:

```python
def _detect_my_framework(repo_path: Path) -> dict | None:
    if (repo_path / "my-marker-file").exists():
        return {"language": "my_framework", "detected_by": ["my-marker-file"]}
    return None
```

Call it inside `detect()` before the `"unknown"` fallback.

## Environment variables

None required for Phase 1.

Phase 2 will add `ANTHROPIC_API_KEY` for Claude-powered suggestions.

## Running tests

```bash
pytest tests/ -v
pytest tests/test_detectors.py -v   # just detectors
pytest tests/test_checks.py -v      # just checks
pytest tests/test_fingerprint.py -v # just fingerprint + scoring
```

## Linting

```bash
ruff check repoaudit/ tests/
ruff format repoaudit/ tests/
```
