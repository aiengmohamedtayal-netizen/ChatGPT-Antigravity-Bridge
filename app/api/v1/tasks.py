"""Tasks API Router for ChatGPT Actions and UI management."""

import asyncio
from datetime import datetime, timezone
import json
from typing import List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.task import Task, ExecutionLog, TaskStatus, TaskPriority
from app.models.project import Project
from app.models.api_key import ApiKey, ApiScope
from app.schemas.task import (
    TaskCreate,
    TaskContinue,
    TaskResponse,
    TaskDetailResponse,
    ExecutionLogResponse,
)
from app.core.dependencies import (
    get_current_api_key,
    require_scopes,
    get_client_ip,
    get_idempotency_key,
)
from app.core.audit import record_audit_event
from app.core.errors import NotFoundError, ConflictError
from app.orchestration.orchestrator import orchestrator
from app.orchestration.logger import execution_logger

router = APIRouter(prefix="/tasks", tags=["Tasks"])


def _calculate_duration(task: Task) -> Optional[float]:
    if task.started_at:
        started = task.started_at
        if started.tzinfo is not None:
            started = started.astimezone(timezone.utc).replace(tzinfo=None)
        completed = task.completed_at
        if completed is not None and completed.tzinfo is not None:
            completed = completed.astimezone(timezone.utc).replace(tzinfo=None)
        end_time = completed or datetime.now(timezone.utc).replace(tzinfo=None)
        return round((end_time - started).total_seconds(), 2)
    return None


@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create & dispatch task (ChatGPT Action)",
    description="Submit an architectural task or development prompt to Antigravity.",
)
async def create_task(
    payload: TaskCreate,
    request: Request,
    idempotency_key: Optional[str] = Depends(get_idempotency_key),
    api_key: ApiKey = Depends(require_scopes([ApiScope.TASKS_CREATE])),
    db: Session = Depends(get_db),
):
    # Idempotency check
    if idempotency_key:
        existing = db.query(Task).filter(Task.idempotency_key == idempotency_key).first()
        if existing:
            return existing

    # Verify project exists
    project = db.query(Project).filter(Project.id == payload.project_id).first()
    if not project:
        raise NotFoundError(
            detail=f"Project with ID '{payload.project_id}' does not exist.",
            code="PROJECT_NOT_FOUND",
        )

    task = Task(
        project_id=payload.project_id,
        prompt=payload.prompt,
        priority=payload.priority or TaskPriority.NORMAL,
        parent_task_id=payload.parent_task_id,
        status=TaskStatus.QUEUED,
        idempotency_key=idempotency_key,
        metadata_json=payload.metadata or {},
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    # Record audit log
    record_audit_event(
        db=db,
        actor=api_key.name,
        action="TASK_CREATE",
        resource_type="task",
        resource_id=task.id,
        ip_address=get_client_ip(request),
        details={"project_id": task.project_id, "priority": task.priority},
    )

    # Dispatch to orchestrator queue
    await orchestrator.enqueue_task(task.id, task.priority)

    resp = TaskResponse.model_validate(task)
    resp.duration_seconds = _calculate_duration(task)
    return resp


@router.get(
    "",
    response_model=List[TaskResponse],
    summary="List tasks",
    description="Retrieve a list of tasks filtered by project or status.",
)
async def list_tasks(
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    api_key: ApiKey = Depends(require_scopes([ApiScope.TASKS_READ])),
    db: Session = Depends(get_db),
):
    query = db.query(Task)
    if project_id:
        query = query.filter(Task.project_id == project_id)
    if status:
        query = query.filter(Task.status == status)

    tasks = query.order_by(Task.created_at.desc()).offset(offset).limit(limit).all()
    results = []
    for t in tasks:
        item = TaskResponse.model_validate(t)
        item.duration_seconds = _calculate_duration(t)
        results.append(item)
    return results


@router.get(
    "/{task_id}",
    response_model=TaskDetailResponse,
    summary="Get task details & output",
    description="Inspect execution logs, status, code diffs, and final Antigravity response.",
)
async def get_task(
    task_id: str,
    api_key: ApiKey = Depends(require_scopes([ApiScope.TASKS_READ])),
    db: Session = Depends(get_db),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise NotFoundError(detail=f"Task '{task_id}' not found.", code="TASK_NOT_FOUND")

    resp = TaskDetailResponse.model_validate(task)
    resp.duration_seconds = _calculate_duration(task)
    return resp


@router.post(
    "/{task_id}/continue",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Continue task conversationally",
    description="Send a follow-up prompt to Antigravity inside the existing session/context.",
)
async def continue_task(
    task_id: str,
    payload: TaskContinue,
    request: Request,
    api_key: ApiKey = Depends(require_scopes([ApiScope.TASKS_CREATE])),
    db: Session = Depends(get_db),
):
    parent = db.query(Task).filter(Task.id == task_id).first()
    if not parent:
        raise NotFoundError(detail=f"Parent task '{task_id}' not found.", code="PARENT_NOT_FOUND")

    # Create continuation task
    child = Task(
        project_id=parent.project_id,
        prompt=payload.prompt,
        priority=payload.priority or parent.priority,
        parent_task_id=parent.id,
        session_id=parent.session_id,
        status=TaskStatus.QUEUED,
    )
    db.add(child)
    db.commit()
    db.refresh(child)

    record_audit_event(
        db=db,
        actor=api_key.name,
        action="TASK_CONTINUE",
        resource_type="task",
        resource_id=child.id,
        ip_address=get_client_ip(request),
        details={"parent_task_id": parent.id, "session_id": parent.session_id},
    )

    await orchestrator.enqueue_task(child.id, child.priority)

    resp = TaskResponse.model_validate(child)
    resp.duration_seconds = _calculate_duration(child)
    return resp


@router.post(
    "/{task_id}/cancel",
    response_model=TaskResponse,
    summary="Cancel a task",
    description="Abort a running or queued task.",
)
async def cancel_task(
    task_id: str,
    request: Request,
    api_key: ApiKey = Depends(require_scopes([ApiScope.TASKS_CANCEL])),
    db: Session = Depends(get_db),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise NotFoundError(detail=f"Task '{task_id}' not found.", code="TASK_NOT_FOUND")

    success = await orchestrator.cancel_task(task_id)
    db.refresh(task)

    record_audit_event(
        db=db,
        actor=api_key.name,
        action="TASK_CANCEL",
        resource_type="task",
        resource_id=task.id,
        status="success" if success else "failed",
        ip_address=get_client_ip(request),
    )

    resp = TaskResponse.model_validate(task)
    resp.duration_seconds = _calculate_duration(task)
    return resp


@router.get(
    "/{task_id}/events",
    summary="Real-time Server-Sent Events (SSE)",
    description="Stream live execution logs and state transitions for a task.",
)
async def stream_task_events(task_id: str, request: Request, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise NotFoundError(detail=f"Task '{task_id}' not found.", code="TASK_NOT_FOUND")

    queue = execution_logger.subscribe(task_id)

    async def event_generator():
        try:
            # First send existing logs
            logs = db.query(ExecutionLog).filter(ExecutionLog.task_id == task_id).order_by(ExecutionLog.id).all()
            for l in logs:
                data = {
                    "id": l.id,
                    "task_id": l.task_id,
                    "timestamp": l.timestamp.isoformat(),
                    "level": l.level,
                    "message": l.message,
                    "tool_name": l.tool_name,
                    "step_index": l.step_index,
                }
                yield f"event: log\ndata: {json.dumps(data)}\n\n"

            # Stream live incoming logs
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event_data = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"event: log\ndata: {json.dumps(event_data)}\n\n"
                except asyncio.TimeoutError:
                    # Heartbeat
                    yield ": ping\n\n"
        finally:
            execution_logger.unsubscribe(task_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
