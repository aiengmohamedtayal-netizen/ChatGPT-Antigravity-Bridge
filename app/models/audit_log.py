"""SQLAlchemy model for Security & Operational Audit Logging."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class AuditLog(Base):
    """AuditLog tracks security events, administrative changes, and task dispatches."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=utc_now, index=True)
    actor = Column(String(128), nullable=False)  # API Key prefix, IP, system
    action = Column(String(64), nullable=False, index=True)  # TASK_CREATE, TASK_CANCEL, KEY_GEN, etc.
    resource_type = Column(String(64), nullable=False)  # task, project, api_key, connection
    resource_id = Column(String(64), nullable=True)
    status = Column(String(16), default="success", nullable=False)
    ip_address = Column(String(64), nullable=True)
    details = Column(JSON, nullable=True)
