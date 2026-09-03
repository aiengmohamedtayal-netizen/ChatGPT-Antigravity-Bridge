"""Extensibility adapters for additional coding agents (Claude Code, Gemini CLI, Codex)."""

import asyncio
from typing import Any, AsyncGenerator, Dict, Optional
from app.providers.base import AgentEvent, BaseAgentProvider


class ClaudeCodeProvider(BaseAgentProvider):
    """Adapter stub for Anthropic Claude Code CLI."""

    provider_id: str = "claude_code"
    display_name: str = "Claude Code CLI Adapter"

    async def check_health(self) -> Dict[str, Any]:
        return {"status": "degraded", "message": "Claude Code CLI adapter ready for integration.", "latency_ms": 0.0}

    async def create_session(self, workspace_path: str, session_id: Optional[str] = None) -> str:
        return session_id or "claude_sess_01"

    async def execute_task(
        self,
        task_id: str,
        session_id: str,
        prompt: str,
        workspace_path: str,
        context: Optional[str] = None,
        is_continuation: bool = False,
    ) -> AsyncGenerator[AgentEvent, None]:
        yield AgentEvent(event_type="status", message="Dispatching to Claude Code CLI...", level="info")
        await asyncio.sleep(0.5)
        yield AgentEvent(event_type="token", message=f"[Claude Code Adapter] Executed prompt: {prompt}", level="info")

    async def cancel_task(self, task_id: str, session_id: Optional[str] = None) -> bool:
        return True


class GeminiCliProvider(BaseAgentProvider):
    """Adapter stub for Google Gemini CLI."""

    provider_id: str = "gemini_cli"
    display_name: str = "Gemini CLI Adapter"

    async def check_health(self) -> Dict[str, Any]:
        return {"status": "degraded", "message": "Gemini CLI adapter ready for integration.", "latency_ms": 0.0}

    async def create_session(self, workspace_path: str, session_id: Optional[str] = None) -> str:
        return session_id or "gemini_sess_01"

    async def execute_task(
        self,
        task_id: str,
        session_id: str,
        prompt: str,
        workspace_path: str,
        context: Optional[str] = None,
        is_continuation: bool = False,
    ) -> AsyncGenerator[AgentEvent, None]:
        yield AgentEvent(event_type="status", message="Dispatching to Gemini CLI...", level="info")
        await asyncio.sleep(0.5)
        yield AgentEvent(event_type="token", message=f"[Gemini CLI Adapter] Executed prompt: {prompt}", level="info")

    async def cancel_task(self, task_id: str, session_id: Optional[str] = None) -> bool:
        return True
