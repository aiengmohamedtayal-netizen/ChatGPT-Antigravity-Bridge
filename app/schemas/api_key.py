"""Pydantic schemas for API Key creation and management."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from app.models.api_key import ApiScope


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="Label/identifier for this key (e.g. 'ChatGPT Production Action')")
    scopes: List[str] = Field(
        default=[ApiScope.TASKS_CREATE, ApiScope.TASKS_READ, ApiScope.PROJECTS_READ],
        description="Allowed permission scopes",
    )
    expires_in_days: Optional[int] = Field(default=None, ge=1, le=365, description="Optional lifespan in days")


class ApiKeyResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    scopes: List[str]
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ApiKeyCreated(ApiKeyResponse):
    """Returned only once upon initial key generation."""

    raw_key: str = Field(..., description="Full secret API key. Store safely, it will never be displayed again.")
