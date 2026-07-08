from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from poligrapher_app.api.database import Base, engine
from poligrapher_app.api.routers import analysis, policies, providers, schedules
from poligrapher_app.services import scheduler as sched_engine
from poligrapher_app.services.tasks import TaskRegistry

# Built React SPA (produced by `npm run build`); served at / in production.
FRONTEND_DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"


def _ensure_columns() -> None:
    """Add columns introduced after a table was first created (SQLite dev DBs).

    create_all() only creates missing tables, not missing columns, so a
    pre-existing DB needs the newer nullable columns added idempotently.
    """
    inspector = inspect(engine)
    if "providers" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("providers")}
        if "domain" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE providers ADD COLUMN domain VARCHAR(255)"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _ensure_columns()
    app.state.tasks = TaskRegistry()
    sched_engine.init_scheduler(app.state.tasks)
    yield
    sched_engine.shutdown_scheduler()


app = FastAPI(title="Poligrapher", lifespan=lifespan)

# Allow the Vite dev server (separate origin) to call the API during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(providers.router)
app.include_router(policies.router)
app.include_router(analysis.router)
app.include_router(schedules.router)

# Serve the built SPA (index.html + assets) when present. Registered last so it
# doesn't shadow the /api routes. html=True makes client-side routing work.
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="spa")
