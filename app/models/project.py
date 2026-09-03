"""SQLAlchemy model for Project / Workspace management."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.orm import relationship
from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class Project(Base):
    """Project represents a codebase workspace managed by Antigravity."""

    __tablename__ = "projects"

    id = Column(String(64), primary_key=True, default=lambda: f"proj_{uuid.uuid4().hex[:12]}")
    name = Column(String(128), nullable=False)
    workspace_path = Column(String(512), nullable=False)
    description = Column(Text, nullable=True, default="")
    instructions = Column(Text, nullable=True, default="")
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")
