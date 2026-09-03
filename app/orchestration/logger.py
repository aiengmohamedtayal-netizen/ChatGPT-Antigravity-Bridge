"""Execution Logger & Real-time Event Broadcaster (SSE & WebSockets)."""

import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import Any, AsyncGenerator, Dict, Optional, Set
from app import database
from app.models.task import ExecutionLog

logger = logging.getLogger(__name__)


class ExecutionLogger:
    """Buffers logs, commits to database, and broadcasts to active SSE/WebSocket clients."""

    def __init__(self):
        # Map task_id -> set of active asyncio.Queue instances
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}

    def subscribe(self, task_id: str) -> asyncio.Queue:
        """Subscribe to live events for a specific task."""
        queue: asyncio.Queue = asyncio.Queue()
        if task_id not in self._subscribers:
            self._subscribers[task_id] = set()
        self._subscribers[task_id].add(queue)
        return queue

    def unsubscribe(self, task_id: str, queue: asyncio.Queue):
        """Unsubscribe when client disconnects."""
        if task_id in self._subscribers:
            self._subscribers[task_id].discard(queue)
            if not self._subscribers[task_id]:
                del self._subscribers[task_id]

    async def log_and_broadcast(
        self,
        task_id: str,
        message: str,
        level: str = "info",
        tool_name: Optional[str] = None,
        tool_input: Optional[Any] = None,
        tool_output: Optional[Any] = None,
        step_index: int = 0,
    ) -> ExecutionLog:
        """Persist log to database and broadcast event to all subscribers."""
        now = datetime.now(timezone.utc)

        # 1. DB persistence
        db = database.SessionLocal()
        try:
            log_entry = ExecutionLog(
                task_id=task_id,
                timestamp=now,
                level=level,
                message=message,
                tool_name=tool_name,
                tool_input=tool_input,
                tool_output=tool_output,
                step_index=step_index,
            )
            db.add(log_entry)
            db.commit()
            db.refresh(log_entry)
        finally:
            db.close()

        # 2. In-memory broadcast payload
        payload = {
            "id": log_entry.id,
            "task_id": task_id,
            "timestamp": now.isoformat(),
            "level": level,
            "message": message,
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_output": tool_output,
            "step_index": step_index,
        }

        # 3. Notify all listeners
        if task_id in self._subscribers:
            for q in list(self._subscribers[task_id]):
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    pass

        return log_entry


execution_logger = ExecutionLogger()
