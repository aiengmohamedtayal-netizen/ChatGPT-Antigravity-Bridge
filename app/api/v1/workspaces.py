"""Workspaces and Dynamic Filesystem REST API Router."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.api_key import ApiKey, ApiScope
from app.core.dependencies import require_scopes, get_client_ip
from app.core.audit import record_audit_event
from app.services.workspace_service import workspace_service
from app.services.fs_service import fs_service
from app.schemas.workspace import (
    WorkspaceResponse,
    WorkspaceDetailResponse,
    WorkspaceCreate,
    DirectoryListingResponse,
    FileContentResponse,
    FileWriteRequest,
    FileWriteResponse,
    FileMoveRequest,
    FileDeleteRequest,
    SearchResponse,
    FileTreeResponse,
)

router = APIRouter(prefix="/workspaces", tags=["Workspaces & Filesystem"])


@router.get("", response_model=List[WorkspaceResponse], summary="List all authorized workspaces")
async def list_workspaces(
    enabled_only: bool = Query(True, description="Filter only enabled workspaces"),
    api_key: ApiKey = Depends(require_scopes([ApiScope.PROJECTS_READ])),
):
    """List all workspace roots currently authorized for ChatGPT and Antigravity."""
    return fs_service.list_workspaces(enabled_only=enabled_only)


@router.post("", response_model=WorkspaceDetailResponse, status_code=status.HTTP_201_CREATED, summary="Authorize new workspace root")
async def authorize_workspace(
    payload: WorkspaceCreate,
    request: Request,
    api_key: ApiKey = Depends(require_scopes([ApiScope.PROJECTS_WRITE])),
    db: Session = Depends(get_db),
):
    """Dynamically authorize a new directory root for Antigravity & ChatGPT access."""
    ws = workspace_service.register_workspace(
        path=payload.path,
        name=payload.name,
        workspace_id=payload.workspace_id,
        description=payload.description or "",
        instructions=payload.instructions or "",
        enabled=payload.enabled,
    )
    workspace_service.sync_with_db(db)

    record_audit_event(
        db=db,
        actor=api_key.name,
        action="WORKSPACE_AUTHORIZE",
        resource_type="workspace",
        resource_id=ws.id,
        ip_address=get_client_ip(request),
        details={"path": ws.path, "name": ws.name},
    )

    return fs_service.get_workspace(ws.id)


@router.get("/{workspace_id}", response_model=WorkspaceDetailResponse, summary="Get workspace details")
async def get_workspace(
    workspace_id: str,
    api_key: ApiKey = Depends(require_scopes([ApiScope.PROJECTS_READ])),
):
    """Retrieve metadata, instructions, and preview entries for an authorized workspace."""
    return fs_service.get_workspace(workspace_id)


@router.get("/{workspace_id}/files", response_model=DirectoryListingResponse, summary="List directory contents")
async def list_workspace_files(
    workspace_id: str,
    subpath: Optional[str] = Query(None, description="Subpath inside authorized workspace"),
    show_hidden: bool = Query(False, description="Include files starting with ."),
    api_key: ApiKey = Depends(require_scopes([ApiScope.PROJECTS_READ])),
):
    """Safely list folder contents within an authorized workspace."""
    return fs_service.list_directory(path=subpath, workspace_id=workspace_id, show_hidden=show_hidden)


@router.get("/{workspace_id}/file", response_model=FileContentResponse, summary="Read file content")
async def read_workspace_file(
    workspace_id: str,
    path: str = Query(..., description="Path to file inside authorized workspace"),
    max_bytes: int = Query(1_000_000, description="Max bytes to read"),
    offset: int = Query(0, description="Offset in bytes"),
    api_key: ApiKey = Depends(require_scopes([ApiScope.PROJECTS_READ])),
):
    """Safely read text content of an authorized file."""
    return fs_service.read_file(path=path, workspace_id=workspace_id, max_bytes=max_bytes, offset=offset)


@router.post("/{workspace_id}/file", response_model=FileWriteResponse, summary="Write file content")
async def write_workspace_file(
    workspace_id: str,
    payload: FileWriteRequest,
    request: Request,
    api_key: ApiKey = Depends(require_scopes([ApiScope.PROJECTS_WRITE])),
    db: Session = Depends(get_db),
):
    """Safely create or update a file within an authorized workspace."""
    res = fs_service.write_file(
        path=payload.path,
        content=payload.content,
        workspace_id=workspace_id,
        overwrite=payload.overwrite,
    )
    record_audit_event(
        db=db,
        actor=api_key.name,
        action="FILE_WRITE",
        resource_type="file",
        resource_id=res["path"],
        ip_address=get_client_ip(request),
        details={"bytes": res["bytes_written"]},
    )
    return res


@router.delete("/{workspace_id}/file", summary="Delete file or folder")
async def delete_workspace_file(
    workspace_id: str,
    path: str = Query(..., description="Path to file or folder"),
    recursive: bool = Query(False, description="Recursive deletion flag for folders"),
    confirm: bool = Query(False, description="Explicit confirmation required"),
    request: Request = None,
    api_key: ApiKey = Depends(require_scopes([ApiScope.PROJECTS_WRITE])),
    db: Session = Depends(get_db),
):
    """Safely delete a file or directory within an authorized workspace."""
    res = fs_service.delete_file(path=path, workspace_id=workspace_id, recursive=recursive, confirm=confirm)
    record_audit_event(
        db=db,
        actor=api_key.name,
        action="FILE_DELETE",
        resource_type="file",
        resource_id=res["path"],
        ip_address=get_client_ip(request),
    )
    return res


@router.get("/{workspace_id}/tree", response_model=FileTreeResponse, summary="Get workspace directory tree")
async def get_workspace_tree(
    workspace_id: str,
    path: Optional[str] = Query(None, description="Subpath to root tree"),
    max_depth: int = Query(3, ge=1, le=5, description="Max depth (1-5)"),
    api_key: ApiKey = Depends(require_scopes([ApiScope.PROJECTS_READ])),
):
    """Retrieve a bounded, security-isolated directory tree."""
    return fs_service.get_file_tree(path=path, workspace_id=workspace_id, max_depth=max_depth)


@router.get("/{workspace_id}/search", response_model=SearchResponse, summary="Search files in workspace")
async def search_workspace_files(
    workspace_id: str,
    query: str = Query(..., description="Filename pattern or content substring"),
    search_type: str = Query("filename", enum=["filename", "content"]),
    max_results: int = Query(50, ge=1, le=200),
    api_key: ApiKey = Depends(require_scopes([ApiScope.PROJECTS_READ])),
):
    """Search authorized files by name/glob or content."""
    return fs_service.search_files(
        query=query,
        workspace_id=workspace_id,
        search_type=search_type,
        max_results=max_results,
    )
