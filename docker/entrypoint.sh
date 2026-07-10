#!/usr/bin/env bash
set -euo pipefail

# Apply explicit schema migrations before serving traffic.
echo "Applying database migrations..."
alembic upgrade head

# Seed the database from the bundled CSV. migrate_csv is idempotent.
echo "Seeding database..."
python -m poligrapher_app.migrate_csv || echo "Seed step failed (continuing)."

# Hand off to the app. exec so uvicorn is PID 1 and receives stop signals.
echo "Starting poligrapher-app on ${HOST:-0.0.0.0}:${PORT:-8080}..."
exec python -m poligrapher_app
