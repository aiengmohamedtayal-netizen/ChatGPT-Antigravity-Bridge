"""Sessions API Router for managing Antigravity Agent conversational sessions."""

from typing import List
from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.project import Project
from app.models.task import Task, TaskStatus, TaskPriority
from app.models.api_key import ApiKey, ApiScope
from app.core.dependencies import get_current_api_key, require_scopes, get_client_ip
from app.core.audit import record_audit_event
from app.core.errors import NotFoundError
from app.providers.registry import provider_registry
from app.orchestration.orchestrator import orchestrator

router = APIRouter(tags=["Agent Sessions"])


class SessionCreate(BaseModel):
    title: str = Field(default="ChatGPT Session", description="Session label or title")


class SessionMessage(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=20000, description="Instruction for Antigravity Agent")
    priority: str = Field(default=TaskPriority.NORMAL)


@router.get("/projects/{project_id}/sessions", summary="List Agent Sessions for Project")
async def list_project_sessions(
    project_id: str,
    api_key: ApiKey = Depends(require_scopes([ApiScope.PROJECTS_READ])),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise NotFoundError(f"Project '{project_id}' not found.")

    sessions = (
        db.query(Task.session_id)
        .filter(Task.project_id == project_id, Task.session_id.isnot(None))
        .distinct()
        .all()
    )

    data = []
    for s in sessions:
        sid = s[0]
        if not sid:
            continue
        last_task = (
            db.query(Task)
            .filter(Task.session_id == sid)
            .order_by(Task.created_at.desc())
            .first()
        )
        data.append({
            "session_id": sid,
            "project_id": project_id,
            "last_prompt": last_task.prompt[:80] if last_task else "",
            "last_status": last_task.status if last_task else "",
            "created_at": last_task.created_at.isoformat() if last_task and last_task.created_at else None,
        })
    return data


@router.post("/projects/{project_id}/sessions", status_code=status.HTTP_201_CREATED, summary="Create New Agent Session")
async def create_new_session(
    project_id: str,
    payload: SessionCreate,
    request: Request,
    api_key: ApiKey = Depends(require_scopes([ApiScope.TASKS_CREATE])),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise NotFoundError(f"Project '{project_id}' not found.")

    provider = provider_registry.get_provider()
    session_id = await provider.create_session(workspace_path=project.workspace_path)

    record_audit_event(
        db=db,
        actor=api_key.name,
        action="SESSION_CREATE",
        resource_type="session",
        resource_id=session_id,
        ip_address=get_client_ip(request),
        details={"project_id": project.id, "title": payload.title},
    )

    return {
        "session_id": session_id,
        "project_id": project.id,
        "status": "active",
        "title": payload.title,
    }


@router.get("/sessions/{session_id}", summary="Get Session Details & History")
async def get_session(
    session_id: str,
    api_key: ApiKey = Depends(require_scopes([ApiScope.TASKS_READ])),
    db: Session = Depends(get_db),
):
    tasks = (
        db.query(Task)
        .filter(Task.session_id == session_id)
        .order_by(Task.created_at.asc())
        .all()
    )
    if not tasks:
        raise NotFoundError(f"Session '{session_id}' not found.")

    return {
        "session_id": session_id,
        "project_id": tasks[0].project_id,
        "total_tasks": len(tasks),
        "history": [
            {
                "task_id": t.id,
                "prompt": t.prompt,
                "status": t.status,
                "summary": (t.antigravity_response or {}).get("summary", ""),
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            }
            for t in tasks
        ],
    }


@router.post("/sessions/{session_id}/messages", status_code=status.HTTP_201_CREATED, summary="Send Message to Agent Session")
async def send_message_to_session(
    session_id: str,
    payload: SessionMessage,
    request: Request,
    api_key: ApiKey = Depends(require_scopes([ApiScope.TASKS_CREATE])),
    db: Session = Depends(get_db),
):
    parent = (
        db.query(Task)
        .filter(Task.session_id == session_id)
        .order_by(Task.created_at.desc())
        .first()
    )
    if not parent:
        raise NotFoundError(f"Session '{session_id}' not found.")

    child = Task(
        project_id=parent.project_id,
        parent_task_id=parent.id,
        session_id=session_id,
        prompt=payload.prompt,
        priority=payload.priority,
        status=TaskStatus.QUEUED,
    )
    db.add(child)
    db.commit()
    db.refresh(child)

    await orchestrator.enqueue_task(child.id, child.priority)

    record_audit_event(
        db=db,
        actor=api_key.name,
        action="SESSION_MESSAGE",
        resource_type="task",
        resource_id=child.id,
        ip_address=get_client_ip(request),
        details={"session_id": session_id},
    )

    return {
        "task_id": child.id,
        "session_id": session_id,
        "project_id": child.project_id,
        "status": "queued",
        "message": "Instruction attached to Antigravity session.",
    }


@router.post("/sessions/{session_id}/cancel", summary="Cancel Session Execution")
async def cancel_session(
    session_id: str,
    api_key: ApiKey = Depends(require_scopes([ApiScope.TASKS_CANCEL])),
    db: Session = Depends(get_db),
):
    running_task = (
        db.query(Task)
        .filter(Task.session_id == session_id, Task.status == TaskStatus.RUNNING)
        .first()
    )
    if not running_task:
        return {"success": False, "message": "No running task in this session"}

    await orchestrator.cancel_task(running_task.id)
    return {"success": True, "task_id": running_task.id, "status": "cancelled"}
