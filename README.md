# poligrapher-app

Privacy policy analysis app — a **React (TypeScript) single-page app** backed by a
**FastAPI JSON API**. Add privacy policies by URL or PDF, run the PoliGraph NLP
pipeline, explore the knowledge graph in an interactive cytoscape viewer, and get
GDPR and custom privacy compliance scores.

## Dependencies

| Package | Role |
|---|---|
| [`UCI-Networking-Group/PoliGraph`](https://github.com/UCI-Networking-Group/PoliGraph) | Original PoliGraph research code by Cui, Trimananda, Markopoulou, and Jordan (USENIX Security 2023) |
| [`lukeblevins/PoliGraph`](https://github.com/lukeblevins/PoliGraph) | Enhanced fork used by this app for HTML/PDF crawling, annotation, and knowledge-graph construction |
| [`lukeblevins/policy-scorer`](https://github.com/lukeblevins/policy-scorer) | GDPR compliance scoring (RQ1–RQ6, 80 violation codes) |

## Setup

```sh
git clone https://github.com/lukeblevins/poligrapher-app
cd poligrapher-app
./setup.sh                 # backend: web + analysis deps, Chromium, model data
cd frontend && npm install # frontend deps
```

`setup.sh` creates a `.venv`, installs backend dependencies, installs the
Playwright Chromium browser, and downloads the ~700 MB poligrapher model files
(`poligrapher-fetch-data`). Requires Python 3.11+ and Node 18+.

The app uses **SQLite by default** — no database server needed. Copy the env file
(optional; only needed to override the defaults):

```sh
cp .env.example .env
```

Development stores retained uploads and raw artifact archives under `./storage`.
Production requires PostgreSQL plus private object storage; SQLite is rejected
when `APP_ENV=production`. Apply schema changes explicitly before starting:

```sh
alembic upgrade head
```

Seed the database from the bundled CSV:

```sh
python -m poligrapher_app.migrate_csv
```

Legacy filesystem artifacts can be previewed and imported idempotently:

```sh
python -m poligrapher_app.migrate_artifacts          # dry run
python -m poligrapher_app.migrate_artifacts --apply  # persist JSON + archives
```

## Running

**Development** (two processes, hot reload on both):

```sh
python -m poligrapher_app            # API on :8000
cd frontend && npm run dev           # SPA on :5173 (proxies /api → :8000)
```

Open `http://localhost:5173`.

**Production** (FastAPI serves the built SPA):

```sh
cd frontend && npm run build         # emits frontend/dist
python -m poligrapher_app            # serves API + SPA on :8000
```

Open `http://localhost:8000`.

## Architecture

The frontend is decoupled from all business logic. In production the FastAPI web
image is lightweight; analysis requests are durable PostgreSQL tasks published
to Azure Queue Storage, which wakes a separate Chromium/ML worker from zero.

```
poligrapher-app/
├── poligrapher_app/               # Python backend
│   ├── api/                       # FastAPI — thin JSON layer
│   │   ├── main.py                #   app factory, CORS, serves built SPA
│   │   ├── database.py            #   SQLAlchemy engine/session (SQLite default)
│   │   ├── models.py schemas.py deps.py utils.py mapping.py
│   │   └── routers/               #   providers, policies, analysis (JSON only)
│   ├── services/                  # business logic (no HTTP/view knowledge)
│   │   ├── pipeline.py            #   PoliGraph orchestration
│   │   ├── scoring.py             #   privacy + GDPR scoring
│   │   ├── graph.py               #   graph → cytoscape JSON, stats, GDPR report
│   │   ├── importer.py            #   CSV → DB
│   │   ├── tasks.py               #   durable task state + queue publisher
│   │   └── task_execution.py      #   worker dispatcher
│   ├── domain/policy_analysis.py  # entity classes (document/result/provider)
│   ├── scoring/                   # in-repo heuristic PrivacyScorer + TOML config
│   ├── migrate_csv.py             # CSV → DB seed command
│   └── policy_list.csv            # seed data
└── frontend/                      # Vite + React + TypeScript SPA
    └── src/
        ├── api/                   # typed fetch client + response types
        ├── hooks/                 # TanStack Query hooks + task polling
        └── components/            # layout, GraphViewer (cytoscape), panels, modals
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the domain entity design and
pipeline data flow.
