# Container image for poligrapher-app (built for Cloud Run, runs anywhere).
# Single container: builds the React SPA, then runs the FastAPI backend which
# serves both the JSON API and the built SPA on one port (same origin, no CORS).
# The app listens on $PORT, which Cloud Run/Fly inject at runtime (default 8080).
#
# Models (~700 MB poligrapher data + spaCy model) and the Playwright Chromium
# browser are baked into the image at build time, so cold starts don't fetch them
# and no persistent storage is required.

# ---- Stage 1: build the frontend ----
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build          # emits /app/frontend/dist

# ---- Stage 2: Python backend runtime ----
# Pin to Debian bookworm: Playwright 1.45.0 officially supports it, so
# `playwright install-deps` resolves the right Debian packages. The plain
# `-slim` tag now points to Debian trixie, which Playwright doesn't recognize —
# it falls back to ubuntu20.04 package names that trixie's apt can't satisfy.
FROM python:3.11-slim-bookworm

# Build-time system deps: git (for the git+https PoliGraph / policy-scorer deps)
# and a compiler toolchain for any packages without wheels. Playwright's Chromium
# OS libraries are installed further down (needs root, before we drop privileges).
RUN apt-get update && apt-get install -y --no-install-recommends \
        git build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright's Chromium system libraries as root (apt), before switching
# to the unprivileged user. Both crawl paths (poligrapher's html_crawler and the
# app's acquisition service) launch Chromium. Pinned to pyproject's playwright.
RUN pip install --no-cache-dir playwright==1.45.0 \
    && playwright install-deps chromium

# Run as a non-root user with UID 1000. Create the app dir (incl. the writable
# data/ dir) as root and hand it to `user` now: a later `WORKDIR /home/user/app`
# would otherwise create it root-owned, and the unprivileged user couldn't write
# the SQLite DB into it.
RUN useradd -m -u 1000 user \
    && mkdir -p /home/user/app/data \
    && chown -R user:user /home/user/app
USER user

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PLAYWRIGHT_BROWSERS_PATH=/home/user/.cache/ms-playwright \
    HF_HOME=/home/user/.cache/huggingface \
    HOST=0.0.0.0 \
    PORT=8080 \
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
    && playwright install chromium \
    && poligrapher-fetch-data

# Bundle Readability.js so the crawler never fetches it from GitHub at runtime
# (raw.githubusercontent.com 429-rate-limits shared datacenter IPs, failing the
# crawl on cold starts). The files are vendored under docker/readability/ rather
# than downloaded, because Cloud Build's IP hits that same 429 at build time.
# html_crawler reads them via READABILITY_JS_DIR; keep them at the pinned commit
# READABILITY_JS_COMMIT in poligrapher's html_crawler.
ENV READABILITY_JS_DIR=/home/user/.cache/readability
COPY --chown=user docker/readability/ /home/user/.cache/readability/

# Built SPA from stage 1 (served at / by FastAPI).
COPY --chown=user --from=frontend /app/frontend/dist ./frontend/dist

# Writable location for the SQLite demo DB (ephemeral on the free tier).
RUN mkdir -p /home/user/app/data
COPY --chown=user docker/entrypoint.sh ./entrypoint.sh

# Cloud Run (and Fly, etc.) inject their own PORT at runtime, which the app reads;
# 8080 is just the local/default. EXPOSE is documentation — Cloud Run ignores it.
EXPOSE 8080
CMD ["bash", "entrypoint.sh"]
