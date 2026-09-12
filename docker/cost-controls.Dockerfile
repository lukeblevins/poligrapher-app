# Patch the exact deployed images; avoid releasing unrelated workspace changes.
ARG WEB_BASE=ghcr.io/lukeblevins/poligrapher-app@sha256:e0725c991abb508c3095cf0d6accf79fd50095f2c5812d79ace48bf3a2ce48ec
ARG WORKER_BASE=ghcr.io/lukeblevins/poligrapher-app@sha256:48a172d2b2a12ca8c55c0dbdfb10c7bdc3a52a9fb22eda7004aa3b06233dcda9
FROM ${WEB_BASE} AS cost-dispatcher
COPY --chown=user:user poligrapher_app/cost_guard.py poligrapher_app/cost_worker.py poligrapher_app/cost_dispatcher.py /home/user/app/poligrapher_app/
CMD ["python", "-m", "poligrapher_app.cost_dispatcher"]

FROM ${WORKER_BASE} AS cost-worker
COPY --chown=user:user poligrapher_app/worker.py poligrapher_app/cost_worker.py /home/user/app/poligrapher_app/
CMD ["python", "-m", "poligrapher_app.cost_worker"]
