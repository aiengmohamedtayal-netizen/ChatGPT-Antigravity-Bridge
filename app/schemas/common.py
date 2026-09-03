"""Common schemas used across API endpoints."""

from typing import Any, Dict, Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int = 1
    page_size: int = 20
    has_more: bool = False


class HealthStatus(BaseModel):
    status: str = "ok"
    version: str
    environment: str
    antigravity_status: str
    active_sessions_count: int
    running_tasks_count: int
    timestamp: str


class StandardResponse(BaseModel):
    success: bool = True
    message: str = "Operation completed successfully"
    data: Optional[Dict[str, Any]] = None
