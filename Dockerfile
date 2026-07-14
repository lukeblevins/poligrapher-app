# PoliGraph research application images.
#
# `web` contains only FastAPI, PostgreSQL/Blob/Queue clients, acquisition
# metadata helpers, and the compiled SPA. `worker` adds Chromium, Torch, spaCy,
# transformers, PoliGraph, policy-scorer, and downloaded model data. Azure runs
# the worker only while queue messages exist.

FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim-bookworm AS web
RUN useradd -m -u 1000 user \
    && mkdir -p /home/user/app/data \
    && chown -R user:user /home/user/app
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    HOST=0.0.0.0 \
    PORT=8080 \
    RELOAD=false \
    DATABASE_URL=sqlite:////home/user/app/data/poligrapher.db
WORKDIR /home/user/app
COPY --chown=user:user pyproject.toml ./
COPY --chown=user:user poligrapher_app ./poligrapher_app
COPY --chown=user:user alembic.ini ./
COPY --chown=user:user alembic ./alembic
RUN pip install --user --no-cache-dir .
COPY --chown=user:user --from=frontend /app/frontend/dist ./frontend/dist
COPY --chown=user:user docker/entrypoint.sh ./entrypoint.sh
EXPOSE 8080
CMD ["bash", "entrypoint.sh"]

# Chromium runtime libraries shared by the worker builder and final worker.
FROM python:3.11-slim-bookworm AS worker-runtime
RUN pip install --no-cache-dir playwright==1.45.0 \
    && playwright install-deps chromium \
    && pip uninstall -y playwright pyee greenlet \
    && rm -rf /root/.cache /var/lib/apt/lists/*

FROM worker-runtime AS worker-builder
RUN apt-get update && apt-get install -y --no-install-recommends git build-essential \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 user \
    && mkdir -p /home/user/app \
    && chown -R user:user /home/user/app
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PLAYWRIGHT_BROWSERS_PATH=/home/user/.cache/ms-playwright \
    HF_HOME=/home/user/.cache/huggingface
WORKDIR /home/user/app
RUN pip install --user --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch
COPY --chown=user:user pyproject.toml ./
COPY --chown=user:user poligrapher_app ./poligrapher_app
COPY --chown=user:user alembic.ini ./
COPY --chown=user:user alembic ./alembic
RUN pip install --user --no-cache-dir '.[analysis]'
RUN python -m spacy download en_core_web_md \
    && playwright install chromium \
    && poligrapher-fetch-data

FROM worker-runtime AS worker
RUN useradd -m -u 1000 user \
    && mkdir -p /home/user/app \
    && chown -R user:user /home/user/app
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PLAYWRIGHT_BROWSERS_PATH=/home/user/.cache/ms-playwright \
    HF_HOME=/home/user/.cache/huggingface \
    READABILITY_JS_DIR=/home/user/.cache/readability
WORKDIR /home/user/app
COPY --chown=user:user --from=worker-builder /home/user/.local /home/user/.local
COPY --chown=user:user --from=worker-builder /home/user/.cache /home/user/.cache
COPY --chown=user:user poligrapher_app ./poligrapher_app
COPY --chown=user:user alembic.ini ./
COPY --chown=user:user alembic ./alembic
COPY --chown=user:user docker/readability/ /home/user/.cache/readability/
CMD ["python", "-m", "poligrapher_app.worker"]

# Preserve a useful default for `docker build .` while CI selects explicit
# `web` and `worker` targets.
FROM web AS production
