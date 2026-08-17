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

1. **Configure a provider source** (`PATCH /api/providers/{id}/source`) — stores
   the canonical privacy-policy URL used for website analysis. The source can
   also be discovered from the provider's domain and checked independently.
2. **Start a run** (`POST /api/providers/{id}/runs`) — the API writes a durable
   task and queue message. A worker fetches the source once, then builds and
   scores two related `Policy` records: one from the live HTML and one from a PDF
   rendering of that same capture. Their shared `run_group` keeps the comparison
   together in history.
3. **Upload a PDF** (`POST /api/providers/{id}/uploads`) — stores the source in
   private object storage and queues a single-method analysis. Manual and
   scheduled runs use the same task and persistence infrastructure.
4. **Persist results** — the worker stores graph/results data on the policy rows
   and uploads source files and artifact archives to private object storage.
   Temporary pipeline workspaces are discarded after persistence.
5. **View** — the SPA fetches JSON:
   - `GET /api/policies/{id}/graph` → cytoscape `elements` (rendered client-side)
   - `GET /api/policies/{id}/stats` → graph statistics
   - `GET /api/policies/{id}/assessments` → privacy + GDPR + readability
   - `GET /api/policies/{id}/graph-artifacts` → public graph-only ZIP rebuilt from the retained Blob archive

Tasks are durable `TaskRecord` rows. Production publishes task IDs to Azure Queue
Storage; local development executes the same dispatcher in a thread. Clients
poll `GET /api/tasks/{task_id}`, so status survives web scale-to-zero restarts.
Captured worker output is available from `GET /api/tasks/{task_id}/output`.
Known credential values and their encoded forms are redacted before output is
persisted. Retained source and artifact downloads remain protected by the
`EXPORT_TOKEN` bearer credential.
The graph-only ZIP is public because the canonical graph is already public. A
strict filename allowlist prevents source captures, HTML, PDFs, accessibility
data, logs, and the protected full artifact archive from crossing that boundary.

## Persistence

SQLAlchemy 2.0 ORM over **SQLite by default** and PostgreSQL in production.
Production schema changes are Alembic migrations; canonical graph/results and
task state are stored in PostgreSQL, while source PDFs and artifact archives are
private Blob objects.

Older policy CRUD, generate, and score endpoints remain available as a
compatibility API for imported records and non-SPA clients. The current SPA uses
the provider source, run, upload, and schedule endpoints above.

## Frontend

Vite + React + TypeScript. TanStack Query manages server state and task polling; a
typed fetch client mirrors the API schemas. The graph viewer renders the
`/graph` JSON with cytoscape.js (node types DATA/ACTOR/`we`; edge types
COLLECT/SUBSUM/SUBSUM_BY/COREF), theme-reactive to the OS preference. In
development the Vite dev server proxies `/api` to the FastAPI process; in
production FastAPI serves the built `frontend/dist`.
