#!/usr/bin/env bash
# dev-setup.sh — set up repoaudit for local development
set -euo pipefail

echo "Setting up repoaudit development environment..."

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e .

echo ""
echo "Done. Activate with: source .venv/bin/activate"
echo "Then run: repoaudit analyze /path/to/repo"
echo "Or run tests: pytest tests/ -v"
