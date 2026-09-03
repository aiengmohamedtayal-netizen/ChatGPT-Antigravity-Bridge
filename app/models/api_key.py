"""SQLAlchemy model for API Key authentication and RBAC scopes."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, JSON
from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class ApiScope:
    TASKS_CREATE = "tasks:create"
    TASKS_READ = "tasks:read"
    TASKS_CANCEL = "tasks:cancel"
    PROJECTS_READ = "projects:read"
    PROJECTS_WRITE = "projects:write"
    ADMIN = "admin"

    ALL_SCOPES = [
        TASKS_CREATE,
        TASKS_READ,
        TASKS_CANCEL,
        PROJECTS_READ,
        PROJECTS_WRITE,
        ADMIN,
    ]


class ApiKey(Base):
    """ApiKey stores hashed authentication credentials and permission scopes."""

    __tablename__ = "api_keys"

    id = Column(String(64), primary_key=True, default=lambda: f"key_{uuid.uuid4().hex[:12]}")
    name = Column(String(128), nullable=False)
    key_prefix = Column(String(32), nullable=False)
    hashed_key = Column(String(128), nullable=False, unique=True, index=True)
    scopes = Column(JSON, nullable=False, default=lambda: [ApiScope.TASKS_CREATE, ApiScope.TASKS_READ])
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utc_now)
    last_used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
