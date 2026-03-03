from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialise shared clients (DynamoDB, S3, …) here later
    yield
    # Shutdown: close connections here later


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
from app.api.routes import agents, marketplace, runs, users

app.include_router(users.router,        prefix="/users",        tags=["Users"])
app.include_router(agents.router,       prefix="/agents",       tags=["Agents"])
app.include_router(runs.router,         prefix="/agents",       tags=["AgentRuns"])
app.include_router(marketplace.router,  prefix="/marketplace",  tags=["Marketplace"])
# POST /agents/chat replaces POST /orchestrator/chat (now on the agents router)

# Uncomment when implemented:
# from app.api.routes import connections
# app.include_router(connections.router,  prefix="/connections",  tags=["Connections"])  # Incremental 2


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health() -> dict:
    return {"status": "ok", "version": settings.app_version}
