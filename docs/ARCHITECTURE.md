# Architecture

poligrapher-app is a **React SPA + FastAPI JSON API**. The React frontend owns all
view concerns; the backend exposes JSON and holds the analysis logic. The heavy
NLP/graph work (PoliGraph, policy-scorer) runs server-side.

## Layers (backend)

```
api/        FastAPI — thin HTTP layer. Routers validate input, call services,
            and return Pydantic-modeled JSON. No business logic lives here.
services/   Business logic, decoupled from HTTP and view. Each module is
            independently testable:
              pipeline.py  — runs the 4-stage PoliGraph pipeline for a policy
              scoring.py   — privacy (in-repo) + GDPR (policy-scorer) scoring
              graph.py     — graph artifacts → cytoscape JSON, stats, GDPR report
              importer.py  — policy_list CSV → Provider/Policy rows
              tasks.py     — in-memory background task registry (thread pool)
domain/     Entity classes (PolicyDocumentInfo, PolicyAnalysisResult,
            PolicyDocumentProvider) that encapsulate artifact paths and text
            extraction, hiding filesystem conventions from callers.
scoring/    In-repo heuristic PrivacyScorer + its TOML rules/criteria.
```

`api/mapping.py` is the single conversion point between a DB `Policy` row and a
`PolicyDocumentInfo` domain object, keeping routers and background tasks in sync.

## Data flow

1. **Add policy** (`POST /api/providers/{id}/policies`) — records a `Policy` row
   (URL or uploaded PDF) and computes its artifact directory
   `output/<Provider_Slug>/<date>_<source>/`.
2. **Generate** (`POST /api/policies/{id}/generate`) — a background task runs
   `services.pipeline.generate_graph`, which drives PoliGraph
   (crawl/parse → init → annotate → build graph) and writes
   `graph-original.full.yml`, `graph-original.yml`, and `graph-original.graphml`
   into the policy's output dir.
3. **Score** (`POST /api/policies/{id}/score`) — a background task runs
   `services.scoring.score_privacy` and `score_gdpr`, persisting results as
   `AnalysisResult` rows and updating the policy's scores.
4. **View** — the SPA fetches JSON:
   - `GET /api/policies/{id}/graph` → cytoscape `elements` (rendered client-side)
   - `GET /api/policies/{id}/stats` → graph statistics
   - `GET /api/policies/{id}/assessments` → privacy + GDPR + readability

Background tasks are tracked by `services.tasks.TaskRegistry` (on
`app.state.tasks`) and polled via `GET /api/tasks/{task_id}`.

## Persistence

SQLAlchemy 2.0 ORM over **SQLite by default** (dialect-agnostic `Uuid`/`JSON`
columns, so Postgres works by changing `DATABASE_URL`). Three tables: `providers`,
`policies`, `analysis_results`. Schema is created at startup via
`Base.metadata.create_all`.

## Frontend

Vite + React + TypeScript. TanStack Query manages server state and task polling; a
typed fetch client mirrors the API schemas. The graph viewer renders the
`/graph` JSON with cytoscape.js (node types DATA/ACTOR/`we`; edge types
COLLECT/SUBSUM/SUBSUM_BY/COREF), theme-reactive to the OS preference. In
development the Vite dev server proxies `/api` to the FastAPI process; in
production FastAPI serves the built `frontend/dist`.
