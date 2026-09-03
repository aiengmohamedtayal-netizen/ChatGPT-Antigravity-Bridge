"""SQLAlchemy model for Antigravity Connection Profiles."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, Float, Text
from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class ConnectionStatus:
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    ERROR = "error"


class ConnectionConfig(Base):
    """Configuration and state for an Antigravity instance connection."""

    __tablename__ = "connection_configs"

    id = Column(String(64), primary_key=True, default=lambda: f"conn_{uuid.uuid4().hex[:12]}")
    name = Column(String(128), nullable=False)
    provider_type = Column(String(32), default="antigravity", nullable=False)  # antigravity, simulated, claude_code, gemini_cli
    endpoint_url = Column(String(512), nullable=True)
    cli_path = Column(String(512), nullable=True)
    brain_dir = Column(String(512), nullable=True)
    encrypted_credentials = Column(Text, nullable=True)

    status = Column(String(32), default=ConnectionStatus.DISCONNECTED, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    latency_ms = Column(Float, nullable=True)
    last_ping_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
