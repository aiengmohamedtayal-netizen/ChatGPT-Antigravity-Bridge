"""Projects and Workspaces API Router."""

from typing import List
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.project import Project
from app.models.task import Task
from app.models.api_key import ApiKey, ApiScope
from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectResponse, ProjectContext
from app.core.dependencies import get_current_api_key, require_scopes, get_client_ip
from app.core.audit import record_audit_event
from app.core.errors import NotFoundError
from app.orchestration.context_manager import context_manager

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create project workspace",
)
async def create_project(
    payload: ProjectCreate,
    request: Request,
    api_key: ApiKey = Depends(require_scopes([ApiScope.PROJECTS_WRITE])),
    db: Session = Depends(get_db),
):
    project = Project(
        name=payload.name,
        workspace_path=payload.workspace_path,
        description=payload.description or "",
        instructions=payload.instructions or "",
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    record_audit_event(
        db=db,
        actor=api_key.name,
        action="PROJECT_CREATE",
        resource_type="project",
        resource_id=project.id,
        ip_address=get_client_ip(request),
        details={"name": project.name, "path": project.workspace_path},
    )

    resp = ProjectResponse.model_validate(project)
    resp.active_tasks_count = 0
    return resp


@router.get("", response_model=List[ProjectResponse], summary="List projects")
async def list_projects(
    api_key: ApiKey = Depends(require_scopes([ApiScope.PROJECTS_READ])),
    db: Session = Depends(get_db),
):
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    results = []
    for p in projects:
        count = db.query(Task).filter(Task.project_id == p.id, Task.status.in_(["queued", "running"])).count()
        item = ProjectResponse.model_validate(p)
        item.active_tasks_count = count
        results.append(item)
    return results


@router.get("/{project_id}", response_model=ProjectResponse, summary="Get project details")
async def get_project(
    project_id: str,
    api_key: ApiKey = Depends(require_scopes([ApiScope.PROJECTS_READ])),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise NotFoundError(detail=f"Project '{project_id}' not found.", code="PROJECT_NOT_FOUND")

    count = db.query(Task).filter(Task.project_id == project.id, Task.status.in_(["queued", "running"])).count()
    resp = ProjectResponse.model_validate(project)
    resp.active_tasks_count = count
    return resp


@router.put("/{project_id}", response_model=ProjectResponse, summary="Update project")
async def update_project(
    project_id: str,
    payload: ProjectUpdate,
    request: Request,
    api_key: ApiKey = Depends(require_scopes([ApiScope.PROJECTS_WRITE])),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise NotFoundError(detail=f"Project '{project_id}' not found.", code="PROJECT_NOT_FOUND")

    if payload.name is not None:
        project.name = payload.name
    if payload.workspace_path is not None:
        project.workspace_path = payload.workspace_path
    if payload.description is not None:
        project.description = payload.description
    if payload.instructions is not None:
        project.instructions = payload.instructions

    db.commit()
    db.refresh(project)

    record_audit_event(
        db=db,
        actor=api_key.name,
        action="PROJECT_UPDATE",
        resource_type="project",
        resource_id=project.id,
        ip_address=get_client_ip(request),
    )

    resp = ProjectResponse.model_validate(project)
    return resp


@router.delete("/{project_id}", summary="Delete project")
async def delete_project(
    project_id: str,
    request: Request,
    api_key: ApiKey = Depends(require_scopes([ApiScope.PROJECTS_WRITE])),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise NotFoundError(detail=f"Project '{project_id}' not found.", code="PROJECT_NOT_FOUND")

    db.delete(project)
    db.commit()

    record_audit_event(
        db=db,
        actor=api_key.name,
        action="PROJECT_DELETE",
        resource_type="project",
        resource_id=project_id,
        ip_address=get_client_ip(request),
    )

    return {"success": True, "message": f"Project '{project_id}' deleted."}


@router.get("/{project_id}/context", response_model=ProjectContext, summary="Inspect project context (for ChatGPT)")
async def inspect_project_context(
    project_id: str,
    api_key: ApiKey = Depends(require_scopes([ApiScope.PROJECTS_READ])),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise NotFoundError(detail=f"Project '{project_id}' not found.", code="PROJECT_NOT_FOUND")

    # Deep scan
    scan = context_manager.inspect_workspace(project.workspace_path)
    # Active sessions
    sessions = (
        db.query(Task.session_id)
        .filter(Task.project_id == project_id, Task.session_id.isnot(None))
        .distinct()
        .all()
    )
    # Recent tasks
    recent = (
        db.query(Task)
        .filter(Task.project_id == project_id)
        .order_by(Task.created_at.desc())
        .limit(5)
        .all()
    )

    return ProjectContext(
        project_id=project.id,
        name=project.name,
        workspace_path=project.workspace_path,
        instructions=project.instructions or scan.get("discovered_instructions", ""),
        exists_on_disk=scan.get("exists", False),
        tracked_files_summary=scan.get("summary", []),
        active_sessions=[s[0] for s in sessions if s[0]],
        recent_tasks=[
            {"id": t.id, "prompt": t.prompt[:80], "status": t.status}
            for t in recent
        ],
    )
