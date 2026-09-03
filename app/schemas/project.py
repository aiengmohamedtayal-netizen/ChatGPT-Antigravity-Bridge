"""Pydantic schemas for Projects and Workspace Context."""

from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class ProjectBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="Human-readable project name")
    workspace_path: str = Field(..., min_length=1, max_length=512, description="Absolute filesystem directory path")
    description: Optional[str] = Field(default="", description="High-level description of the repository")
    instructions: Optional[str] = Field(default="", description="Architectural rules, coding guidelines, AGENTS.md content")


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    workspace_path: Optional[str] = None
    description: Optional[str] = None
    instructions: Optional[str] = None


class ProjectResponse(ProjectBase):
    id: str
    created_at: datetime
    updated_at: datetime
    active_tasks_count: Optional[int] = 0

    model_config = {"from_attributes": True}


class ProjectContext(BaseModel):
    """Deep context structure returned to ChatGPT to inspect repository state."""

    project_id: str
    name: str
    workspace_path: str
    instructions: str
    exists_on_disk: bool
    tracked_files_summary: List[str] = []
    active_sessions: List[str] = []
    recent_tasks: List[Dict] = []
