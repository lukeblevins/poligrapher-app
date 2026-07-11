#!/usr/bin/env bash
set -euo pipefail

PYTHON=${PYTHON:-python3}

# Create venv if it doesn't exist

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    "$PYTHON" -m venv .venv
fi

VENV_PYTHON=.venv/bin/python
VENV_BIN=.venv/bin

echo "Installing dependencies..."
"$VENV_PYTHON" -m pip install -e '.[analysis,test]'

echo "Downloading spaCy model..."
"$VENV_PYTHON" -m spacy download en_core_web_md

echo "Installing Playwright browser..."
"$VENV_BIN/playwright" install chromium

echo "Downloading poligrapher model data (~700MB)..."
"$VENV_BIN/poligrapher-fetch-data"

if command -v npm >/dev/null 2>&1; then
    echo "Installing frontend dependencies..."
    (cd frontend && npm install)
else
    echo "npm not found — skipping frontend install (install Node 18+, then 'cd frontend && npm install')."
fi

echo ""
echo "Setup complete. To start the app (development):"
echo "  source .venv/bin/activate"
echo "  python -m poligrapher_app          # API on :8000"
echo "  (cd frontend && npm run dev)       # SPA on :5173"
