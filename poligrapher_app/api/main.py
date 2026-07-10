from contextlib import asynccontextmanager
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from poligrapher_app.api.database import Base, engine
from poligrapher_app.api.routers import analysis, policies, providers, runs, schedules
from poligrapher_app.services import scheduler as sched_engine
from poligrapher_app.services.tasks import TaskRegistry

# Built React SPA (produced by `npm run build`); served at / in production.
FRONTEND_DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("APP_ENV", "development").lower() != "production":
        Base.metadata.create_all(bind=engine)
    app.state.tasks = TaskRegistry()
    scheduler_enabled = os.getenv("SCHEDULER_ENABLED", "true").lower() in ("1", "true", "yes")
    if scheduler_enabled:
        sched_engine.init_scheduler(app.state.tasks)
    yield
    if scheduler_enabled:
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
app.include_router(runs.router)

# Serve the built SPA (index.html + assets) when present. Registered last so it
# doesn't shadow the /api routes. html=True makes client-side routing work.
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="spa")
