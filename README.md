# repoaudit

A language-agnostic CLI tool that audits any codebase and produces a structured
report covering AI-readiness, security hygiene, developer experience, and test
quality. Zero config required — point it at a repo and get useful output
immediately.

## Quick start

### Docker (recommended — works on any OS)

```bash
# Analyze a repo
docker run -v ./my-repo:/repo ghcr.io/repoaudit/repoaudit analyze /repo

# Save markdown report
docker run \
  -v ./my-repo:/repo \
  -v ./output:/output \
  ghcr.io/repoaudit/repoaudit analyze /repo --output /output/report.md

# Extract fingerprint JSON
docker run -v ./my-repo:/repo ghcr.io/repoaudit/repoaudit fingerprint /repo
```

### Local install (Python 3.11+)

```bash
pip install repoaudit

repoaudit analyze /path/to/repo
repoaudit analyze /path/to/repo --output report.md
repoaudit fingerprint /path/to/repo
repoaudit analyze /path/to/repo --verbose
```

## GitHub Actions

Copy one of the ready-to-use workflow files from the
[`github-actions/`](github-actions/) directory into your repo's
`.github/workflows/` folder.

### Basic (no API key needed)

```bash
cp github-actions/repoaudit-single.yml .github/workflows/repoaudit.yml
```

repoaudit will run on every PR and post the report as a PR comment.

### With AI analysis

```bash
cp github-actions/repoaudit-single-ai.yml .github/workflows/repoaudit.yml
```

Then add `ANTHROPIC_API_KEY` as a repository secret:
**Settings → Secrets and variables → Actions → New repository secret**

### Multi-repo / mono-repo

```bash
cp github-actions/repoaudit-multi.yml .github/workflows/repoaudit.yml
```

Edit the `REPO_PATHS` env var at the top to list the directories to analyze.
The report is uploaded as a workflow artifact.

---

## CLI reference

```
repoaudit analyze <repo_path> [--output FILE] [--verbose] [--format markdown|prompt]

  Analyze a repository and print findings to stdout (or write to FILE).
  Use --format prompt to append a self-contained LLM prompt after the report.

repoaudit fingerprint <repo_path> [--format json|prompt] [--output FILE]

  Extract a structured fingerprint. Default output is JSON.
  Use --format prompt to generate a self-contained prompt you can paste into
  Claude, ChatGPT, or any other LLM — no API key required.
```

### Prompt-output mode

Generate a self-contained prompt for any LLM — no API key needed in the tool:

```bash
# Print prompt to stdout and paste it into your LLM of choice
repoaudit fingerprint /path/to/repo --format prompt

# Save to a file
repoaudit fingerprint /path/to/repo --format prompt --output analysis-prompt.txt

# Append prompt section to the Markdown report
repoaudit analyze /path/to/repo --format prompt
```

## What gets checked

| Category | What it looks for |
|---|---|
| **AI Readiness** | CLAUDE.md / AI instructions, substantial README, consistent naming, env var documentation |
| **Security** | Hardcoded secrets, committed .env files, unpinned dependencies, `latest` Docker tags |
| **Dev Experience** | docker-compose.yml, Dockerfile, seed script, local setup docs, Makefile / yarn scripts |
| **Testing** | tests/ directory, test config, behavior-driven test naming, CI that runs tests |

## Scoring

- `required` checks — weight 3
- `recommended` checks — weight 1
- `optional` checks — shown in report but do not affect score

Score per category = (sum of weights of passed checks) / (total possible weight) * 100

## Supported languages / frameworks

Auto-detected from file layout — no config needed:

- `python_django` — manage.py + settings.py
- `python_flask` — app.py or wsgi.py + requirements.txt
- `python_fastapi` — main.py + fastapi in requirements
- `python` — requirements.txt or pyproject.toml
- `typescript_next` — next.config.*
- `typescript_react` — package.json + src/ + .tsx files
- `typescript` — tsconfig.json
- `kotlin_spring` — build.gradle.kts + src/main/kotlin
- `go` — go.mod
- `dotnet` — *.csproj or *.sln
- `unknown` — fallback

## Getting started (local development)

```bash
git clone <repo>
cd analyze-your-codebase

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .

# Run against this repo (eats own dogfood)
repoaudit analyze .

# Run tests
pytest tests/ -v
```

### Docker development

```bash
docker compose run repoaudit analyze /repo
```

## Adding a new check

1. Pick the right module under `repoaudit/checks/` (or create a new one for a
   new category).
2. Subclass `Check` from `repoaudit.checks.base` and implement `run()`.
3. Register the class in `repoaudit/checks/__init__.py` inside `ALL_CHECKS`.

## Adding a new language

Edit `repoaudit/detectors/language.py`. Add a new `_detect_*` helper function
following the existing pattern and call it inside `detect()` before the
`"unknown"` fallback.

## Phase 2 (planned)

- Per-finding remediation hints powered by the LLM
- Trend tracking: compare fingerprints over time
- Dashboard / web UI for multi-repo results
