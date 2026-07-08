# Hugging Face Spaces (Docker SDK) image for poligrapher-app.
# Single container: builds the React SPA, then runs the FastAPI backend which
# serves both the JSON API and the built SPA on one port (same origin, no CORS).
#
# Models (~700 MB poligrapher data + spaCy model) and the Playwright Firefox
# browser are baked into the image at build time, so cold starts are fast and no
# persistent storage is required.

# ---- Stage 1: build the frontend ----
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build          # emits /app/frontend/dist

# ---- Stage 2: Python backend runtime ----
FROM python:3.11-slim

# Build-time system deps: git (for the git+https PoliGraph / policy-scorer deps)
# and a compiler toolchain for any packages without wheels. Playwright's Firefox
# OS libraries are installed further down (needs root, before we drop privileges).
RUN apt-get update && apt-get install -y --no-install-recommends \
        git build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright's Firefox system libraries as root (apt), before switching
# to the unprivileged user. Pinned to match pyproject's playwright version.
RUN pip install --no-cache-dir playwright==1.45.0 \
    && playwright install-deps firefox

# HF Spaces convention: run as a non-root user with UID 1000.
RUN useradd -m -u 1000 user
USER user

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PLAYWRIGHT_BROWSERS_PATH=/home/user/.cache/ms-playwright \
    HF_HOME=/home/user/.cache/huggingface \
    HOST=0.0.0.0 \
    PORT=7860 \
    RELOAD=false \
    DATABASE_URL=sqlite:////home/user/app/data/poligrapher.db

WORKDIR /home/user/app

# Install the CPU-only torch build first so the project install below reuses it
# instead of pulling the default wheel and its ~2 GB of bundled CUDA libraries —
# useless on a CPU Space, and it bloats the image and build time.
RUN pip install --user --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu torch

# Install the backend (this pulls PoliGraph, policy-scorer, spaCy, etc.; torch is
# already satisfied by the CPU wheel above). Copy only what the install needs
# first so this layer caches across SPA-only changes.
COPY --chown=user pyproject.toml ./
COPY --chown=user poligrapher_app ./poligrapher_app
RUN pip install --user --no-cache-dir .

# Bake models + browser into the image (user-owned caches).
RUN python -m spacy download en_core_web_md \
    && playwright install firefox \
    && poligrapher-fetch-data

# Built SPA from stage 1 (served at / by FastAPI).
COPY --chown=user --from=frontend /app/frontend/dist ./frontend/dist

# Writable location for the SQLite demo DB (ephemeral on the free tier).
RUN mkdir -p /home/user/app/data
COPY --chown=user docker/entrypoint.sh ./entrypoint.sh

EXPOSE 7860
CMD ["bash", "entrypoint.sh"]
