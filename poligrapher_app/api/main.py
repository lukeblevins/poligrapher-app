from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from poligrapher_app.api.database import Base, engine
from poligrapher_app.api.routers import analysis, policies, providers
from poligrapher_app.services.tasks import TaskRegistry

# Built React SPA (produced by `npm run build`); served at / in production.
FRONTEND_DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    app.state.tasks = TaskRegistry()
    yield


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

# Serve the built SPA (index.html + assets) when present. Registered last so it
# doesn't shadow the /api routes. html=True makes client-side routing work.
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="spa")
