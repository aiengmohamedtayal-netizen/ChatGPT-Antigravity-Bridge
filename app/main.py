"""Central FastAPI application entrypoint for ChatGPT × Antigravity Bridge."""

from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
import time
import uuid
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.database import init_db, SessionLocal
from app.models.project import Project
from app.models.api_key import ApiKey, ApiScope
from app.core.security import generate_api_key
from app.core.rate_limit import limiter
from app.core.errors import BridgeException, bridge_exception_handler
from app.api.v1.router import v1_router
from app.mcp.server import mcp_router
from app.api.websockets import ws_router
from app.orchestration.orchestrator import orchestrator

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("antigravity.bridge")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager: database init, seed defaults, queue worker."""
    logger.info("Initializing ChatGPT × Antigravity Bridge...")
    init_db()

    # Seed default project if empty
    db = SessionLocal()
    try:
        existing_project = db.query(Project).first()
        if not existing_project:
            workspace_dir = os.path.abspath(os.getcwd())
            default_proj = Project(
                id="proj_default",
                name="Default Workspace",
                workspace_path=workspace_dir,
                description="Default workspace directory for ChatGPT × Antigravity Bridge.",
                instructions="Follow clean architecture, write modular and tested code, never delete working code.",
            )
            db.add(default_proj)
            db.commit()
            logger.info("Created default project workspace: %s", default_proj.id)

        # Seed default administrative API key if no keys exist
        existing_key = db.query(ApiKey).first()
        if not existing_key:
            raw_key, hashed_key, prefix = generate_api_key()
            admin_key = ApiKey(
                id="key_admin_init",
                name="Default Admin & ChatGPT Key",
                key_prefix=prefix,
                hashed_key=hashed_key,
                scopes=ApiScope.ALL_SCOPES,
                is_active=True,
            )
            db.add(admin_key)
            db.commit()
            logger.info("=" * 60)
            logger.info("INITIAL API KEY GENERATED (Save this for ChatGPT Custom GPT setup):")
            logger.info("Key: %s", raw_key)
            logger.info("=" * 60)
            # Store temporary file for convenience in development mode
            with open(".initial_api_key.txt", "w", encoding="utf-8") as f:
                f.write(f"INITIAL_API_KEY={raw_key}\n")
    finally:
        db.close()

    # Start task orchestrator background worker
    orchestrator.start_worker()

    yield

    # Shutdown queue worker
    await orchestrator.stop_worker()
    logger.info("Bridge application shutdown completed.")


settings = get_settings()
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=settings.APP_DESCRIPTION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Attach rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_exception_handler(BridgeException, bridge_exception_handler)

# CORS middleware
origins = settings.CORS_ORIGINS if isinstance(settings.CORS_ORIGINS, list) else [settings.CORS_ORIGINS]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Content-Disposition"],
)


# Security and Request Tracing Middleware
@app.middleware("http")
async def request_tracing_and_security_headers(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    t0 = time.perf_counter()

    response: Response = await call_next(request)

    latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # Log structured HTTP summary
    logger.info(
        '[%s] %s %s -> %d (%.2fms)',
        request_id[:8],
        request.method,
        request.url.path,
        response.status_code,
        latency_ms,
    )
    return response


# Mount Routers
app.include_router(v1_router)
app.include_router(mcp_router)
app.include_router(ws_router)


# Health Check
@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


# OAuth & Discovery Probes for OpenAI MCP Connector
@app.get("/.well-known/oauth-protected-resource", include_in_schema=False)
@app.get("/.well-known/oauth-protected-resource/{path:path}", include_in_schema=False)
@app.get("/mcp/sse/.well-known/oauth-protected-resource", include_in_schema=False)
@app.get("/.well-known/oauth-authorization-server", include_in_schema=False)
@app.get("/.well-known/oauth-authorization-server/{path:path}", include_in_schema=False)
@app.get("/mcp/sse/.well-known/oauth-authorization-server", include_in_schema=False)
@app.get("/.well-known/openid-configuration", include_in_schema=False)
@app.get("/.well-known/openid-configuration/{path:path}", include_in_schema=False)
@app.get("/mcp/sse/.well-known/openid-configuration", include_in_schema=False)
async def oauth_discovery_fallback():
    return JSONResponse(status_code=200, content={"authorization_servers": []})


# Static Assets, Developer Dashboard & 3D Landing Page
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_landing():
        landing_file = static_dir / "landing.html"
        if landing_file.exists():
            return FileResponse(landing_file)
        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return JSONResponse({"status": "healthy", "message": "Service online."})

    @app.get("/landing", include_in_schema=False)
    async def serve_landing_alias():
        landing_file = static_dir / "landing.html"
        if landing_file.exists():
            return FileResponse(landing_file)
        return FileResponse(static_dir / "index.html")

    @app.get("/dashboard", include_in_schema=False)
    async def serve_dashboard():
        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return JSONResponse({"status": "healthy", "message": "Dashboard under construction."})
