"""Task Orchestration Engine, Priority Queue Worker, and Lifecycle State Machine."""

import asyncio
from datetime import datetime, timezone
import logging
from typing import Dict, Optional
from sqlalchemy.orm import Session
from app import database
from app.models.task import Task, TaskPriority, TaskStatus
from app.models.project import Project
from app.providers.registry import provider_registry
from app.orchestration.context_manager import context_manager
from app.orchestration.logger import execution_logger

logger = logging.getLogger(__name__)

PRIORITY_MAP = {
    TaskPriority.URGENT: 0,
    TaskPriority.HIGH: 1,
    TaskPriority.NORMAL: 2,
    TaskPriority.LOW: 3,
}


class TaskOrchestrator:
    """Core task orchestration layer managing queue execution, state machine, and agent dispatch."""

    def __init__(self):
        self._queue: Optional[asyncio.PriorityQueue] = None
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._worker_task: Optional[asyncio.Task] = None
        self._is_running: bool = False

    def _get_queue(self) -> asyncio.PriorityQueue:
        if self._queue is None:
            self._queue = asyncio.PriorityQueue()
        return self._queue

    def start_worker(self):
        """Start the background orchestration queue worker."""
        if not self._is_running:
            self._is_running = True
            self._queue = asyncio.PriorityQueue()
            self._cleanup_zombie_tasks()
            self._worker_task = asyncio.create_task(self._process_queue_loop())
            logger.info("TaskOrchestrator worker started.")

    def _cleanup_zombie_tasks(self):
        """Reset any tasks left in 'running' state from previous process run."""
        try:
            db = database.SessionLocal()
            try:
                zombies = db.query(Task).filter(Task.status == TaskStatus.RUNNING).all()
                for z in zombies:
                    z.status = TaskStatus.FAILED
                    z.completed_at = datetime.now(timezone.utc)
                    z.error_info = {
                        "code": "SERVER_RESTARTED",
                        "message": "Task cancelled due to gateway server restart.",
                    }
                if zombies:
                    db.commit()
                    logger.info("Cleaned up %d zombie running tasks on startup.", len(zombies))
            finally:
                db.close()
        except Exception as e:
            logger.warning("Failed to clean up zombie tasks on startup: %s", e)

    async def stop_worker(self):
        """Gracefully shut down queue worker and cancel running jobs."""
        self._is_running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        for tid, job in list(self._running_tasks.items()):
            job.cancel()
        logger.info("TaskOrchestrator worker stopped.")

    async def enqueue_task(self, task_id: str, priority: str = TaskPriority.NORMAL):
        """Enqueue task by priority."""
        weight = PRIORITY_MAP.get(priority, 2)
        # Store tuple (weight, timestamp, task_id)
        queue = self._get_queue()
        await queue.put((weight, datetime.now(timezone.utc).timestamp(), task_id))
        logger.info("Enqueued task %s with priority %s (weight: %d)", task_id, priority, weight)

    async def _process_queue_loop(self):
        """Continuous loop processing queued tasks according to priority."""
        queue = self._get_queue()
        while self._is_running:
            try:
                weight, ts, task_id = await queue.get()
                # Run execution as a managed background task
                job = asyncio.create_task(self._run_task_lifecycle(task_id))
                self._running_tasks[task_id] = job
                job.add_done_callback(lambda _, tid=task_id: self._running_tasks.pop(tid, None))
                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in orchestrator queue loop: %s", e)
                await asyncio.sleep(0.5)

    async def _run_task_lifecycle(self, task_id: str):
        """Execute task state machine and provider adapter."""
        db: Session = database.SessionLocal()
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                logger.warning("Task %s not found in database during run", task_id)
                return

            if task.status == TaskStatus.CANCELLED:
                logger.info("Task %s was cancelled before start", task_id)
                return

            # State transition: queued -> running
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now(timezone.utc)
            db.commit()

            project = db.query(Project).filter(Project.id == task.project_id).first()
            if not project:
                task.status = TaskStatus.FAILED
                task.error_info = {"code": "PROJECT_NOT_FOUND", "message": f"Project {task.project_id} not found"}
                task.completed_at = datetime.now(timezone.utc)
                db.commit()
                return

            # Continuation handling
            parent_summary = None
            is_continuation = False
            if task.parent_task_id:
                parent_task = db.query(Task).filter(Task.id == task.parent_task_id).first()
                if parent_task:
                    is_continuation = True
                    task.session_id = parent_task.session_id
                    if parent_task.antigravity_response:
                        parent_summary = parent_task.antigravity_response.get("summary")

            # Enrich and normalize prompt
            normalized = context_manager.assemble_normalized_prompt(
                project=project,
                raw_prompt=task.prompt,
                parent_task_summary=parent_summary,
            )
            task.normalized_prompt = normalized

            # Log validation stage
            await execution_logger.log_and_broadcast(
                task_id=task.id,
                message=f"Task verified and normalized. Starting execution in project '{project.name}'...",
                level="info",
                step_index=0,
            )

            # Resolve Agent Provider
            provider = provider_registry.get_provider()
            session_id = await provider.create_session(
                workspace_path=project.workspace_path,
                session_id=task.session_id,
            )
            task.session_id = session_id
            db.commit()

            # Execute via provider and stream logs/events
            full_response_text = []
            files_modified = []
            artifacts = []

            async for event in provider.execute_task(
                task_id=task.id,
                session_id=session_id,
                prompt=task.prompt,
                workspace_path=project.workspace_path,
                context=normalized,
                is_continuation=is_continuation,
            ):
                # Broadcast and persist event
                await execution_logger.log_and_broadcast(
                    task_id=task.id,
                    message=event.message,
                    level=event.level,
                    tool_name=event.tool_name,
                    tool_input=event.tool_input,
                    tool_output=event.tool_output,
                    step_index=event.step_index,
                )

                if event.event_type == "token":
                    full_response_text.append(event.message)
                elif event.event_type == "tool_call" and event.tool_name == "write_to_file":
                    target = (event.tool_input or {}).get("target_file") or (event.tool_input or {}).get("target")
                    if target and target not in files_modified:
                        files_modified.append(target)

            # Check if cancelled during execution
            db.refresh(task)
            if task.status == TaskStatus.CANCELLED:
                await execution_logger.log_and_broadcast(
                    task_id=task.id,
                    message="Task execution was cancelled.",
                    level="warning",
                )
                return

            # State transition: running -> completed
            final_text = "".join(full_response_text).strip()
            summary = final_text[:300] + ("..." if len(final_text) > 300 else "")
            if not summary:
                summary = "Task executed successfully by Antigravity."

            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now(timezone.utc)
            task.antigravity_response = {
                "summary": summary,
                "full_text": final_text,
                "files_modified": files_modified,
                "artifacts": artifacts,
                "session_id": session_id,
            }
            db.commit()

            await execution_logger.log_and_broadcast(
                task_id=task.id,
                message=f"Task completed successfully. Result ready for ChatGPT review.",
                level="info",
                step_index=99,
            )

        except Exception as e:
            logger.error("Error executing task %s: %s", task_id, e, exc_info=True)
            db.rollback()
            try:
                task = db.query(Task).filter(Task.id == task_id).first()
                if task:
                    task.status = TaskStatus.FAILED
                    task.completed_at = datetime.now(timezone.utc)
                    task.error_info = {
                        "code": "EXECUTION_EXCEPTION",
                        "message": str(e),
                        "retryable": True,
                    }
                    db.commit()
                    await execution_logger.log_and_broadcast(
                        task_id=task.id,
                        message=f"Task execution failed: {str(e)}",
                        level="error",
                        step_index=99,
                    )
            except Exception:
                pass
        finally:
            db.close()

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a running or queued task."""
        db: Session = database.SessionLocal()
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                return False

            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                return False

            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.now(timezone.utc)
            db.commit()

            # Abort active running job if any
            if task_id in self._running_tasks:
                self._running_tasks[task_id].cancel()

            # Notify provider
            provider = provider_registry.get_provider()
            await provider.cancel_task(task_id, task.session_id)

            await execution_logger.log_and_broadcast(
                task_id=task_id,
                message="Task cancelled by user/API request.",
                level="warning",
            )
            return True
        finally:
            db.close()


orchestrator = TaskOrchestrator()
