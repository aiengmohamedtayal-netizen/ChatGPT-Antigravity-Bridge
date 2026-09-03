"""Secondary/Fallback Antigravity Provider using native CLI / AgentAPI."""

import asyncio
import json
import logging
import os
import subprocess
from typing import Any, AsyncGenerator, Dict, List, Optional
from app.config import get_settings
from app.providers.base import AgentEvent, BaseAgentProvider

logger = logging.getLogger(__name__)


class AntigravityCliProvider(BaseAgentProvider):
    """
    Secondary/Fallback Antigravity Adapter.
    Uses native agentapi.bat executable and brain transcript observer.
    """

    provider_id: str = "antigravity_cli"
    display_name: str = "Antigravity CLI / AgentAPI (Fallback)"

    def __init__(self):
        self.settings = get_settings()
        self.cli_path = self.settings.ANTIGRAVITY_AGENTAPI_PATH
        self.brain_dir = self.settings.ANTIGRAVITY_BRAIN_DIR

    async def check_health(self) -> Dict[str, Any]:
        """Check if agentapi.bat executable exists on disk."""
        exists = os.path.exists(self.cli_path)
        return {
            "status": "connected" if exists else "disconnected",
            "cli_installed": exists,
            "path": self.cli_path,
            "message": "CLI available" if exists else f"CLI binary not found at {self.cli_path}",
            "latency_ms": 5.0 if exists else 0.0,
        }

    async def create_session(self, workspace_path: str, session_id: Optional[str] = None) -> str:
        """Create a new Antigravity conversation via agentapi.bat."""
        if session_id:
            return session_id

        if not os.path.exists(self.cli_path):
            return f"cli_sess_{os.urandom(4).hex()}"

        try:
            # Run agentapi.bat new-conversation --title="ChatGPT Bridge" "Initialize"
            cmd = [self.cli_path, "new-conversation", "--title=ChatGPT Bridge Session", "Initialize bridge session"]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            output = stdout.decode("utf-8")
            # Try to parse conversation ID from output
            for line in output.splitlines():
                if "conversation_id" in line.lower() or "id:" in line.lower():
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        return parts[-1].strip('",')
        except Exception as e:
            logger.warning("Failed to spawn CLI session via agentapi: %s", e)

        return f"cli_sess_{os.urandom(4).hex()}"

    async def execute_task(
        self,
        task_id: str,
        session_id: str,
        prompt: str,
        workspace_path: str,
        context: Optional[str] = None,
        is_continuation: bool = False,
    ) -> AsyncGenerator[AgentEvent, None]:
        """Send prompt to Antigravity via agentapi send-message or new-conversation."""
        yield AgentEvent(
            event_type="status",
            message=f"Dispatching task to Antigravity CLI (session: {session_id})...",
            level="info",
            step_index=0,
        )

        if not os.path.exists(self.cli_path):
            yield AgentEvent(
                event_type="log",
                message=f"Antigravity CLI not found at {self.cli_path}; running simulation mode...",
                level="warning",
                step_index=1,
            )
            yield AgentEvent(
                event_type="token",
                message=f"[CLI Simulation] Task completed for prompt: '{prompt[:80]}...'",
                step_index=2,
            )
            return

        try:
            action = "send-message" if is_continuation else "new-conversation"
            cmd = [self.cli_path, action, session_id, prompt] if is_continuation else [self.cli_path, action, prompt]

            yield AgentEvent(
                event_type="log",
                message=f"Executing CLI command: {' '.join(cmd[:3])}...",
                level="info",
                step_index=1,
            )

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                out_text = stdout.decode("utf-8").strip()
                yield AgentEvent(
                    event_type="token",
                    message=out_text or "Task executed successfully via Antigravity CLI.",
                    level="info",
                    step_index=2,
                )
            else:
                err_text = stderr.decode("utf-8").strip()
                yield AgentEvent(
                    event_type="log",
                    message=f"CLI execution error (code {proc.returncode}): {err_text}",
                    level="error",
                    step_index=99,
                )
        except Exception as e:
            yield AgentEvent(
                event_type="log",
                message=f"CLI dispatch failed: {str(e)}",
                level="error",
                step_index=99,
            )

    async def cancel_task(self, task_id: str, session_id: Optional[str] = None) -> bool:
        return True
