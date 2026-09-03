"""Pydantic schemas for Antigravity Connection status and settings."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ConnectionConfigBase(BaseModel):
    name: str
    provider_type: str = Field(default="antigravity", description="antigravity, simulated, claude_code, gemini_cli")
    endpoint_url: Optional[str] = None
    cli_path: Optional[str] = None
    brain_dir: Optional[str] = None


class ConnectionConfigCreate(ConnectionConfigBase):
    credentials_secret: Optional[str] = None


class ConnectionConfigUpdate(BaseModel):
    name: Optional[str] = None
    provider_type: Optional[str] = None
    endpoint_url: Optional[str] = None
    cli_path: Optional[str] = None
    brain_dir: Optional[str] = None
    credentials_secret: Optional[str] = None
    is_active: Optional[bool] = None


class ConnectionConfigResponse(ConnectionConfigBase):
    id: str
    status: str
    is_active: bool
    latency_ms: Optional[float] = None
    last_ping_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConnectionHealthCheck(BaseModel):
    status: str
    provider: str
    latency_ms: float
    message: str
    details: Optional[dict] = None
