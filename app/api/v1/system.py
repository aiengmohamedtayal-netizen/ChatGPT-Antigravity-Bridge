"""System health, provider connectivity, and management endpoints."""

from datetime import datetime, timezone
import time
from typing import Dict, List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.task import Task, TaskStatus
from app.models.project import Project
from app.models.api_key import ApiKey, ApiScope
from app.core.dependencies import get_current_api_key, require_scopes
from app.providers.registry import provider_registry
from app.config import get_settings

router = APIRouter(prefix="/system", tags=["System & Providers"])


@router.get("/status", summary="System & Connection Health Status")
async def get_system_status(db: Session = Depends(get_db)):
    """Public/internal health check for bridge and agent connectivity."""
    settings = get_settings()
    provider = provider_registry.get_provider()

    t0 = time.perf_counter()
    health = await provider.check_health()
    ping_latency = round((time.perf_counter() - t0) * 1000, 2)

    running_tasks = db.query(Task).filter(Task.status == TaskStatus.RUNNING).count()
    queued_tasks = db.query(Task).filter(Task.status == TaskStatus.QUEUED).count()
    total_projects = db.query(Project).count()

    active_sessions = (
        db.query(Task.session_id)
        .filter(Task.session_id.isnot(None))
        .distinct()
        .count()
    )

    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "app_version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "active_provider": {
            "id": provider.provider_id,
            "display_name": provider.display_name,
            "status": health.get("status", "unknown"),
            "latency_ms": ping_latency,
            "details": health,
        },
        "stats": {
            "running_tasks": running_tasks,
            "queued_tasks": queued_tasks,
            "active_sessions": active_sessions,
            "total_projects": total_projects,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/providers", summary="List Available Agent Providers")
async def list_providers(api_key: ApiKey = Depends(get_current_api_key)):
    """List all registered agent provider adapters."""
    return provider_registry.list_providers()


@router.post("/ping", summary="Ping Active Agent Provider")
async def ping_provider(api_key: ApiKey = Depends(get_current_api_key)):
    """Run real-time ping against the configured implementation provider."""
    provider = provider_registry.get_provider()
    t0 = time.perf_counter()
    health = await provider.check_health()
    latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    return {
        "provider": provider.provider_id,
        "display_name": provider.display_name,
        "latency_ms": latency_ms,
        "health": health,
    }


@router.post("/switch-provider", summary="Switch Active Provider")
async def switch_provider(
    provider_id: str,
    api_key: ApiKey = Depends(require_scopes([ApiScope.ADMIN])),
):
    """Dynamically change the active agent provider."""
    settings = get_settings()
    # verify existence
    provider = provider_registry.get_provider(provider_id)
    settings.DEFAULT_AGENT_PROVIDER = provider.provider_id
    return {
        "success": True,
        "active_provider": provider.provider_id,
        "display_name": provider.display_name,
    }
