"""Pydantic schemas for Authorized Workspaces and Filesystem Operations."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    path: str
    enabled: bool = True
    description: Optional[str] = ""
    exists_on_disk: bool = False
    top_level_entries_count: int = 0


class WorkspaceDetailResponse(BaseModel):
    id: str
    name: str
    path: str
    enabled: bool = True
    description: Optional[str] = ""
    instructions: Optional[str] = ""
    exists_on_disk: bool = False
    preview_entries: List[Dict[str, Any]] = []


class WorkspaceCreate(BaseModel):
    path: str = Field(..., description="Absolute local filesystem directory path to authorize")
    name: Optional[str] = Field(None, description="Human-readable workspace label")
    workspace_id: Optional[str] = Field(None, description="Custom identifier (e.g. proj_analytics)")
    description: Optional[str] = Field("", description="Description of the project/workspace")
    instructions: Optional[str] = Field("", description="Custom architectural guidelines")
    enabled: bool = True


class FileEntry(BaseModel):
    name: str
    path: str
    relative_path: str
    is_dir: bool
    size_bytes: Optional[int] = None
    modified_at: Optional[str] = None


class DirectoryListingResponse(BaseModel):
    directory: str
    workspace_root: str
    total_entries: int
    entries: List[FileEntry]


class FileContentResponse(BaseModel):
    path: str
    relative_path: str
    workspace_root: str
    content: str
    size_bytes: int
    bytes_read: int
    offset: int
    is_truncated: bool


class FileWriteRequest(BaseModel):
    path: str = Field(..., description="Target file path inside authorized workspace")
    content: str = Field(..., description="UTF-8 text content to write")
    overwrite: bool = Field(True, description="Allow overwriting existing files")


class FileWriteResponse(BaseModel):
    success: bool
    path: str
    relative_path: str
    workspace_root: str
    bytes_written: int
    message: str


class FileMoveRequest(BaseModel):
    source_path: str
    target_path: str
    overwrite: bool = False


class FileDeleteRequest(BaseModel):
    path: str
    recursive: bool = False
    confirm: bool = Field(..., description="Explicit confirmation flag required")


class SearchMatch(BaseModel):
    name: str
    path: str
    relative_path: str
    workspace_root: str


class SearchResponse(BaseModel):
    query: str
    search_type: str
    total_matches: int
    results: List[SearchMatch]


class FileTreeResponse(BaseModel):
    root_path: str
    workspace_root: str
    max_depth: int
    total_nodes: int
    tree: Dict[str, Any]
