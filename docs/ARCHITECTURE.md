# Architecture

poligrapher-app is a **React SPA + FastAPI JSON API**. The React frontend owns all
view concerns; the backend exposes JSON and publishes durable tasks. Heavy
NLP/graph work runs in a separate event-driven worker image.

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
              tasks.py     — PostgreSQL task state + local/Azure Queue publisher
              task_execution.py — analysis worker task dispatcher
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
2. **Generate** (`POST /api/policies/{id}/generate`) — the API writes a durable
   task and queue message. An Azure Container Apps Job scales from zero and runs
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

Tasks are durable `TaskRecord` rows. Production publishes task IDs to Azure Queue
Storage; local development executes the same dispatcher in a thread. Clients
poll `GET /api/tasks/{task_id}`, so status survives web scale-to-zero restarts.

## Persistence

SQLAlchemy 2.0 ORM over **SQLite by default** and PostgreSQL in production.
Production schema changes are Alembic migrations; canonical graph/results and
task state are stored in PostgreSQL, while source PDFs and artifact archives are
private Blob objects.

## Frontend

Vite + React + TypeScript. TanStack Query manages server state and task polling; a
typed fetch client mirrors the API schemas. The graph viewer renders the
`/graph` JSON with cytoscape.js (node types DATA/ACTOR/`we`; edge types
COLLECT/SUBSUM/SUBSUM_BY/COREF), theme-reactive to the OS preference. In
development the Vite dev server proxies `/api` to the FastAPI process; in
production FastAPI serves the built `frontend/dist`.
