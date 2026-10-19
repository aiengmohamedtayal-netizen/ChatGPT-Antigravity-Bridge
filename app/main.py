"""Central FastAPI application entrypoint for ChatGPT × Antigravity Bridge."""

import asyncio
from contextlib import asynccontextmanager
import logging
import os
import time
import uuid
from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app import database
from app.models.project import Project
from app.models.api_key import ApiKey, ApiScope
from app.core.security import generate_api_key
from app.core.rate_limit import gateway_rate_limiter, limiter, rate_limit_key_func
from app.core.errors import (
    BridgeException,
    bridge_exception_handler,
    format_jsonrpc_error_payload,
    global_exception_handler,
)
from app.core.telemetry import (
    configure_structured_logging,
    get_correlation_id,
    set_correlation_id,
    telemetry,
)
from app.api.v1.router import v1_router
from app.mcp.server import mcp_bridge_runtime, mcp_router
from app.api.websockets import ws_router
from app.orchestration.orchestrator import orchestrator

settings = get_settings()
configure_structured_logging(
    level=logging.INFO,
    json_output=settings.STRUCTURED_JSON_LOGS,
)
logger = logging.getLogger("antigravity.bridge")


def _initialize_database_and_workspaces() -> int:
    """Synchronous DB initialization and workspace synchronization executed in a worker thread."""
    database.init_db()
    db = database.SessionLocal()
    try:
        from app.services.workspace_service import workspace_service

        workspace_service.sync_with_db(db)
        ws_count = len(workspace_service.list_authorized_workspaces(enabled_only=False))

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
            logger.info(
                "Initial administrative API key generated.",
                extra={"event": "initial_api_key_seeded", "key_prefix": prefix},
            )
            with open(".initial_api_key.txt", "w", encoding="utf-8") as f:
                f.write(f"INITIAL_API_KEY={raw_key}\n")
        return ws_count
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Unified application lifespan manager:
    Concurrently initializes and starts both Antigravity Core (TaskOrchestrator)
    and the ChatGPT MCP Bridge runtime, and guarantees clean teardown on exit.
    """
    set_correlation_id("startup")
    logger.info(
        "Initializing Antigravity Core & ChatGPT MCP Bridge...",
        extra={"event": "lifecycle_startup_begin"},
    )

    ws_count = await asyncio.to_thread(_initialize_database_and_workspaces)
    logger.info(
        "Synchronized %d authorized workspaces with database.",
        ws_count,
        extra={"event": "workspaces_synced", "workspace_count": ws_count},
    )

    # 1. Start Antigravity Core background task orchestrator
    orchestrator.start_worker()

    # 2. Start ChatGPT MCP Bridge background runtime concurrently
    await mcp_bridge_runtime.start()

    logger.info(
        "STARTUP COMPLETE: [Antigravity Core: ONLINE] | [ChatGPT MCP Bridge: ONLINE] — Listening on %s:%s (MCP SSE: %s)",
        settings.HOST,
        os.environ.get("PORT", settings.PORT),
        settings.MCP_SSE_ENDPOINT,
        extra={
            "event": "lifecycle_online",
            "antigravity_core": "online",
            "chatgpt_mcp_bridge": "online",
            "mcp_endpoint": settings.MCP_SSE_ENDPOINT,
        },
    )

    try:
        yield
    finally:
        set_correlation_id("shutdown")
        logger.info(
            "Initiating graceful teardown of ChatGPT MCP Bridge and Antigravity Core...",
            extra={"event": "lifecycle_shutdown_begin"},
        )
        # Drain MCP SSE streams and stop orchestrator concurrently
        await asyncio.gather(
            mcp_bridge_runtime.stop(),
            orchestrator.stop_worker(),
            return_exceptions=True,
        )
        logger.info(
            "SHUTDOWN COMPLETE: [Antigravity Core: OFFLINE] | [ChatGPT MCP Bridge: OFFLINE]",
            extra={"event": "lifecycle_shutdown_complete"},
        )


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=settings.APP_DESCRIPTION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Attach rate limiter and exception handlers
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_exception_handler(BridgeException, bridge_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

# CORS middleware
origins = settings.CORS_ORIGINS if isinstance(settings.CORS_ORIGINS, list) else [settings.CORS_ORIGINS]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Correlation-ID", "Content-Disposition"],
)


def should_serve_html(request: Request) -> bool:
    """
    Strict Accept header negotiation for GET /:
    Guarantees that automated API clients, MCP probes, and test runners ALWAYS
    receive strict JSON, while interactive browsers safely receive the HTML view.
    """
    # 1. Explicit query override
    fmt = request.query_params.get("format", "").lower()
    if fmt == "json":
        return False
    if fmt == "html":
        return True

    # 2. Any request carrying API credentials or XHR markers is an automated client
    if (
        request.headers.get("Authorization")
        or request.headers.get("X-API-Key")
        or request.headers.get("X-Requested-With", "").lower() == "xmlhttprequest"
    ):
        return False

    accept_header = request.headers.get("accept", "")
    if not accept_header:
        return False

    # 3. Parse media ranges and quality factors (q-values)
    html_q = -1.0
    json_q = -1.0
    for item in accept_header.split(","):
        parts = [p.strip() for p in item.split(";") if p.strip()]
        if not parts:
            continue
        mime = parts[0].lower()
        q = 1.0
        for param in parts[1:]:
            if param.lower().startswith("q="):
                try:
                    q = float(param[2:])
                except ValueError:
                    q = 1.0
        if mime in ("text/html", "application/xhtml+xml"):
            html_q = max(html_q, q)
        elif mime in ("application/json", "application/problem+json"):
            json_q = max(json_q, q)

    # Serve HTML only if browser explicitly requested text/html with strictly higher priority than JSON
    return html_q > 0.0 and html_q > json_q


# Security, Rate-Limiting, Timeout, and Correlation Tracing Middleware
@app.middleware("http")
async def request_tracing_and_security_headers(request: Request, call_next):
    incoming_cid = (
        request.headers.get("X-Correlation-ID")
        or request.headers.get("X-Request-ID")
        or f"req_{uuid.uuid4().hex[:12]}"
    )
    cid = set_correlation_id(incoming_cid)
    t0 = time.perf_counter()
    telemetry.record_request_start()

    # 1. Lightweight sliding-window rate-limit check
    client_key = rate_limit_key_func(request)
    allowed, remaining, retry_after = gateway_rate_limiter.check_and_consume(client_key)
    if not allowed:
        telemetry.record_request_end(status_code=429, rate_limited=True)
        logger.warning(
            "Rate limit exceeded for client '%s' on %s %s",
            client_key,
            request.method,
            request.url.path,
            extra={
                "event": "http_rate_limited",
                "method": request.method,
                "path": request.url.path,
                "correlation_id": cid,
            },
        )
        payload = format_jsonrpc_error_payload(
            code=-32029,
            message="Rate Limit Exceeded",
            correlation_id=cid,
            detail=f"Too many requests. Retry after {retry_after}s.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            error_code="RATE_LIMIT_EXCEEDED",
            instance=str(request.url.path),
        )
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content=payload,
            headers={
                "X-Request-ID": cid,
                "X-Correlation-ID": cid,
                "Retry-After": str(int(retry_after) + 1),
            },
        )

    # 2. Enforce request timeout for non-streaming HTTP endpoints
    is_streaming_path = request.url.path.startswith("/mcp/sse") and request.method == "GET"
    try:
        if is_streaming_path:
            response: Response = await call_next(request)
        else:
            response = await asyncio.wait_for(
                call_next(request),
                timeout=settings.REQUEST_TIMEOUT_SECONDS,
            )
    except asyncio.TimeoutError:
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        telemetry.record_request_end(status_code=504, timed_out=True)
        logger.error(
            "Request timed out after %.2fs: %s %s",
            settings.REQUEST_TIMEOUT_SECONDS,
            request.method,
            request.url.path,
            extra={
                "event": "http_request_timeout",
                "method": request.method,
                "path": request.url.path,
                "latency_ms": latency_ms,
                "correlation_id": cid,
            },
        )
        payload = format_jsonrpc_error_payload(
            code=-32000,
            message="Gateway Execution Timeout",
            correlation_id=cid,
            detail=f"Request exceeded maximum allowed duration of {settings.REQUEST_TIMEOUT_SECONDS}s.",
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            error_code="EXECUTION_TIMEOUT",
            instance=str(request.url.path),
        )
        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content=payload,
            headers={
                "X-Request-ID": cid,
                "X-Correlation-ID": cid,
            },
        )
    except Exception as exc:
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        telemetry.record_request_end(status_code=500)
        return await global_exception_handler(request, exc)

    latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    telemetry.record_request_end(status_code=response.status_code)

    response.headers["X-Request-ID"] = cid
    response.headers["X-Correlation-ID"] = cid
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"

    logger.info(
        "[%s] %s %s -> %d (%.2fms)",
        cid[:12],
        request.method,
        request.url.path,
        response.status_code,
        latency_ms,
        extra={
            "event": "http_request_completed",
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
            "correlation_id": cid,
        },
    )
    return response


# Mount Routers
app.include_router(v1_router)
app.include_router(mcp_router)
app.include_router(ws_router)


# Enhanced Health & Dynamic Telemetry Endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    metrics = telemetry.snapshot()
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "correlation_id": get_correlation_id(),
        "components": {
            "antigravity_core": "online" if orchestrator._is_running else "standby",
            "chatgpt_mcp_bridge": "online" if mcp_bridge_runtime.is_running else "standby",
            "active_mcp_sse_sessions": mcp_bridge_runtime.active_session_count,
        },
        "uptime_seconds": metrics["uptime_seconds"],
        "memory": metrics["memory"],
        "telemetry": {
            "http_requests": metrics["http_requests"],
            "tool_executions": metrics["tool_executions"],
        },
    }


# OAuth & Discovery Probes for OpenAI MCP Connector
@app.get("/.well-known/ai-plugin.json", include_in_schema=False)
async def ai_plugin_manifest(request: Request):
    base_url = str(request.base_url).rstrip("/")
    return {
        "schema_version": "v1",
        "name_for_human": "Antigravity Bridge",
        "name_for_model": "antigravity_bridge",
        "description_for_human": "Local coding agent bridge connecting ChatGPT to Google Antigravity.",
        "description_for_model": "Plugin for controlling Google Antigravity to inspect workspaces, dispatch coding tasks, monitor task execution, and manage sessions.",
        "auth": {
            "type": "user_http",
            "authorization_type": "bearer",
        },
        "api": {
            "type": "openapi",
            "url": f"{base_url}/openapi.json",
        },
        "logo_url": f"{base_url}/static/logo.png",
        "contact_email": "support@example.com",
        "legal_info_url": f"{base_url}/legal",
    }


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


# Root Discovery Endpoint (Strict JSON for API clients, HTML for browsers)
@app.get("/", tags=["Root"])
async def root(request: Request):
    payload = {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "mode": "headless",
        "chatgpt_schema": "/api/v1/chatgpt/openapi.json",
        "mcp_endpoint": settings.MCP_SSE_ENDPOINT,
        "docs_url": "/docs",
    }
    if should_serve_html(request):
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{settings.APP_NAME}</title>
  <style>
    :root {{ color-scheme: dark; }}
    body {{
      margin: 0;
      padding: 32px;
      background: #0b0f17;
      color: #e2e8f0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      line-height: 1.6;
    }}
    .wrap {{ max-width: 880px; margin: 0 auto; }}
    .card {{
      background: #111827;
      border: 1px solid #1f2937;
      border-radius: 12px;
      padding: 24px;
      margin-bottom: 20px;
    }}
    .badge {{
      display: inline-block;
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      background: #065f46;
      color: #a7f3d0;
      margin-right: 8px;
    }}
    .badge.skill {{ background: #4c1d95; color: #ddd6fe; }}
    h1 {{ margin: 12px 0 8px; font-size: 24px; color: #f8fafc; }}
    h2 {{ margin: 0 0 12px; font-size: 16px; color: #cbd5e1; }}
    p {{ margin: 0 0 12px; color: #94a3b8; font-size: 14px; }}
    code, pre {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      background: #090d16;
      color: #38bdf8;
      border-radius: 6px;
    }}
    code {{ padding: 2px 6px; font-size: 13px; }}
    pre {{ padding: 14px; overflow-x: auto; border: 1px solid #1e293b; font-size: 13px; margin: 8px 0 0; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; margin-top: 16px; }}
    .link-box {{
      display: block;
      padding: 14px;
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 8px;
      color: #f8fafc;
      text-decoration: none;
      font-size: 14px;
      font-weight: 500;
    }}
    .link-box:hover {{ border-color: #38bdf8; }}
    .link-box span {{ display: block; font-size: 12px; color: #94a3b8; font-weight: 400; margin-top: 4px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <span class="badge">ANTIGRAVITY CORE: ONLINE</span>
      <span class="badge skill">CHATGPT MCP BRIDGE: ONLINE</span>
      <h1>{settings.APP_NAME} (v{settings.APP_VERSION})</h1>
      <p>{settings.APP_DESCRIPTION}</p>
      <div class="grid">
        <a class="link-box" href="/docs">Interactive API Docs <span>OpenAPI 3.1 Swagger UI (/docs)</span></a>
        <a class="link-box" href="/api/v1/chatgpt/openapi.json">ChatGPT Action Schema <span>/api/v1/chatgpt/openapi.json</span></a>
        <a class="link-box" href="/health">Live Telemetry &amp; Health <span>/health JSON metrics</span></a>
      </div>
    </div>
    <div class="card">
      <h2>Unified Runtime Architecture</h2>
      <p>Antigravity Core (Task Orchestrator) and ChatGPT MCP Bridge (<code>{settings.MCP_SSE_ENDPOINT}</code>) are running concurrently in a single asyncio event loop with graceful SIGINT/SIGTERM teardown.</p>
      <pre>[Antigravity Core]   TaskOrchestrator Worker + WorkspaceBoundaryGuard : ONLINE
[ChatGPT MCP Bridge] JSON-RPC 2.0 / SSE ({settings.MCP_SSE_ENDPOINT}) &amp; Stdio        : ONLINE</pre>
    </div>
  </div>
</body>
</html>"""
        return HTMLResponse(content=html_content, status_code=200)
    return payload


