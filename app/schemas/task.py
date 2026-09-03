"""Pydantic schemas for Tasks and Execution Logs."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.models.task import TaskPriority, TaskStatus


class ExecutionLogResponse(BaseModel):
    id: int
    task_id: str
    timestamp: datetime
    level: str
    message: str
    tool_name: Optional[str] = None
    tool_input: Optional[Any] = None
    tool_output: Optional[Any] = None
    step_index: int = 0

    model_config = {"from_attributes": True}


class TaskCreate(BaseModel):
    """Schema for submitting a prompt to Antigravity (used by ChatGPT Action)."""

    project_id: str = Field(..., description="ID of the target project workspace")
    prompt: str = Field(..., min_length=1, max_length=20000, description="Instruction or coding request for Antigravity")
    priority: Optional[str] = Field(default=TaskPriority.NORMAL, description="Task execution priority: low, normal, high, urgent")
    parent_task_id: Optional[str] = Field(default=None, description="Optional ID of preceding task to continue conversational context")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Custom metadata or client-side tracing tags")


class TaskContinue(BaseModel):
    """Schema for continuing an existing Antigravity task/session conversationally."""

    prompt: str = Field(..., min_length=1, max_length=20000, description="Follow-up prompt to run in the same session context")
    priority: Optional[str] = Field(default=TaskPriority.NORMAL, description="Execution priority")


class AntigravityOutput(BaseModel):
    summary: str
    full_text: Optional[str] = None
    files_modified: List[str] = []
    diffs: Optional[str] = None
    artifacts: List[Dict[str, Any]] = []


class TaskResponse(BaseModel):
    """Comprehensive task details returned to ChatGPT or UI."""

    id: str
    project_id: str
    parent_task_id: Optional[str] = None
    session_id: Optional[str] = None
    prompt: str
    normalized_prompt: Optional[str] = None
    priority: str
    status: str
    antigravity_response: Optional[Dict[str, Any]] = None
    error_info: Optional[Dict[str, Any]] = None
    metadata_json: Optional[Dict[str, Any]] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None

    model_config = {"from_attributes": True}


class TaskDetailResponse(TaskResponse):
    logs: List[ExecutionLogResponse] = []
