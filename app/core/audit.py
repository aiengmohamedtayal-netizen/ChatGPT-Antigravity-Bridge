"""Audit logging service for tracking administrative and task actions."""

from typing import Any, Dict, Optional
from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog


def record_audit_event(
    db: Session,
    actor: str,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    status: str = "success",
    ip_address: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> AuditLog:
    """Record an immutable audit log entry."""
    audit_entry = AuditLog(
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        status=status,
        ip_address=ip_address,
        details=details,
    )
    db.add(audit_entry)
    db.commit()
    db.refresh(audit_entry)
    return audit_entry
