#!/usr/bin/env bash
set -euo pipefail

# Seed the SQLite database from the bundled CSV. migrate_csv is idempotent
# (existing rows are skipped), so this is safe on every start — which matters on
# the HF Spaces free tier where the container's disk is ephemeral and resets.
echo "Seeding database..."
python -m poligrapher_app.migrate_csv || echo "Seed step failed (continuing)."

# Hand off to the app. exec so uvicorn is PID 1 and receives stop signals.
echo "Starting poligrapher-app on ${HOST:-0.0.0.0}:${PORT:-7860}..."
exec python -m poligrapher_app
