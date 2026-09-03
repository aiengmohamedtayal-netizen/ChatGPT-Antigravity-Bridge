"""Audit Logs API Router."""

from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.api_key import ApiKey, ApiScope
from app.core.dependencies import require_scopes

router = APIRouter(prefix="/audit-logs", tags=["Audit & Security"])


@router.get("", summary="List Audit Logs")
async def list_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    api_key: ApiKey = Depends(require_scopes([ApiScope.ADMIN])),
    db: Session = Depends(get_db),
):
    logs = (
        db.query(AuditLog)
        .order_by(AuditLog.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        {
            "id": l.id,
            "timestamp": l.timestamp.isoformat() if l.timestamp else None,
            "actor": l.actor,
            "action": l.action,
            "resource_type": l.resource_type,
            "resource_id": l.resource_id,
            "status": l.status,
            "ip_address": l.ip_address,
            "details": l.details,
        }
        for l in logs
    ]
