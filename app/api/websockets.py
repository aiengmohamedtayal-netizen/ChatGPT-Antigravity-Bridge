"""WebSocket endpoint for high-speed bi-directional live task streaming."""

import asyncio
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.database import SessionLocal
from app.models.task import Task, ExecutionLog
from app.orchestration.logger import execution_logger

logger = logging.getLogger(__name__)
ws_router = APIRouter(prefix="/ws", tags=["WebSockets"])


@ws_router.websocket("/tasks/{task_id}")
async def task_websocket_endpoint(websocket: WebSocket, task_id: str):
    """WebSocket streaming endpoint for live logs and events."""
    await websocket.accept()
    queue = execution_logger.subscribe(task_id)

    # First send historical logs
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            await websocket.send_json({"error": f"Task '{task_id}' not found"})
            await websocket.close()
            return

        logs = db.query(ExecutionLog).filter(ExecutionLog.task_id == task_id).order_by(ExecutionLog.id).all()
        for l in logs:
            await websocket.send_json({
                "type": "history_log",
                "id": l.id,
                "timestamp": l.timestamp.isoformat() if l.timestamp else None,
                "level": l.level,
                "message": l.message,
                "tool_name": l.tool_name,
                "step_index": l.step_index,
            })
    finally:
        db.close()

    try:
        while True:
            try:
                # Wait for new live broadcast event or client message
                event_data = await asyncio.wait_for(queue.get(), timeout=20.0)
                await websocket.send_json({"type": "live_log", **event_data})
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        logger.debug("WebSocket client disconnected for task %s", task_id)
    except Exception as e:
        logger.error("WebSocket error on task %s: %s", task_id, e)
    finally:
        execution_logger.unsubscribe(task_id, queue)
