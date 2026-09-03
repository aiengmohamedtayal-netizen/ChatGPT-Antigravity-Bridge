"""SQLAlchemy models for Task Orchestration and Execution Logging."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
)
from sqlalchemy.orm import relationship
from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class TaskStatus:
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_FOR_INPUT = "waiting_for_input"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority:
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class Task(Base):
    """Task represents a discrete or conversational development instruction sent to Antigravity."""

    __tablename__ = "tasks"

    id = Column(String(64), primary_key=True, default=lambda: f"task_{uuid.uuid4().hex[:12]}")
    project_id = Column(String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_task_id = Column(String(64), nullable=True, index=True)
    session_id = Column(String(128), nullable=True, index=True)

    prompt = Column(Text, nullable=False)
    normalized_prompt = Column(Text, nullable=True)
    priority = Column(String(16), default=TaskPriority.NORMAL, nullable=False)
    status = Column(String(32), default=TaskStatus.QUEUED, nullable=False, index=True)

    antigravity_response = Column(JSON, nullable=True)
    error_info = Column(JSON, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    idempotency_key = Column(String(128), nullable=True, index=True)

    created_at = Column(DateTime, default=utc_now, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    project = relationship("Project", back_populates="tasks")
    logs = relationship("ExecutionLog", back_populates="task", cascade="all, delete-orphan", order_by="ExecutionLog.id")


class ExecutionLog(Base):
    """Structured execution log event emitted during task lifecycle."""

    __tablename__ = "execution_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(64), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    timestamp = Column(DateTime, default=utc_now, index=True)
    level = Column(String(16), default="info", nullable=False)
    message = Column(Text, nullable=False)
    tool_name = Column(String(64), nullable=True)
    tool_input = Column(JSON, nullable=True)
    tool_output = Column(JSON, nullable=True)
    step_index = Column(Integer, default=0)

    # Relationship
    task = relationship("Task", back_populates="logs")
