# poligrapher-app

Gradio web interface for privacy policy analysis using [PoliGraph](https://github.com/lukeblevins/PoliGraph). Upload a privacy policy by URL or PDF, run the full NLP pipeline, visualize the resulting knowledge graph, and get GDPR and custom privacy compliance scores.

## Dependencies

| Package | Role |
|---|---|
| [`lukeblevins/PoliGraph`](https://github.com/lukeblevins/PoliGraph) | NLP pipeline: HTML crawling, annotation, graph construction |
| [`lukeblevins/gdpr-policy-scorer`](https://github.com/lukeblevins/gdpr-policy-scorer) | GDPR compliance scoring (RQ1–RQ6, 80 violation codes) |

## Setup

```sh
# Install with all dependencies (requires Python 3.11+)
pip install "git+https://github.com/lukeblevins/poligrapher-app.git"

# Install Playwright browser for HTML crawling
playwright install firefox

# Download poligrapher model data (see PoliGraph repo for link)
# Extract to poligrapher/extra-data/ in the installed package
```

For local development:

```sh
git clone https://github.com/lukeblevins/poligrapher-app
cd poligrapher-app
pip install -e .
playwright install firefox
```

## Running

```sh
python -m poligrapher_app
```

Or directly:

```sh
python poligrapher_app/app.py
```

## Folder layout

```
poligrapher-app/
├── poligrapher_app/
│   ├── app.py               Gradio UI (tabs, callbacks)
│   ├── functions.py         Pipeline orchestration
│   ├── policy_analysis.py   Domain entities (PolicyDocumentInfo, etc.)
│   ├── database.py          Result persistence
│   ├── api_routes.py        FastAPI endpoints
│   ├── validators.py        URL/input validation
│   ├── grades.py            Grade retrieval helpers
│   ├── policy_list.csv      Seed policy list
│   └── analysis/
│       ├── privacy_scorer.py       Custom privacy scoring engine
│       ├── config/scoring_rules.toml
│       └── criteria/scoring_criteria.toml
├── docs/
│   └── ARCHITECTURE.md      Entity class design and data flow
└── pyproject.toml
```

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the domain entity design and pipeline data flow.
