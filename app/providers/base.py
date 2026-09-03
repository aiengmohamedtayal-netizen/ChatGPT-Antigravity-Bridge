"""Abstract base interface and event models for Agent Providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional


@dataclass
class AgentEvent:
    """Event emitted during agent task execution."""

    event_type: str  # 'log', 'thought', 'tool_call', 'tool_result', 'token', 'status'
    message: str
    level: str = "info"
    tool_name: Optional[str] = None
    tool_input: Optional[Any] = None
    tool_output: Optional[Any] = None
    step_index: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AgentTaskResult:
    """Final result of an agent task execution."""

    summary: str
    full_text: Optional[str] = None
    files_modified: List[str] = field(default_factory=list)
    diffs: Optional[str] = None
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    session_id: Optional[str] = None
    raw_response: Optional[Any] = None


class BaseAgentProvider(ABC):
    """Abstract interface that all implementation agent adapters must implement."""

    provider_id: str = "base"
    display_name: str = "Base Agent Provider"

    @abstractmethod
    async def check_health(self) -> Dict[str, Any]:
        """Verify provider availability, connectivity, and latency."""
        pass

    @abstractmethod
    async def create_session(self, workspace_path: str, session_id: Optional[str] = None) -> str:
        """Create or initialize a session/conversation within a workspace root."""
        pass

    @abstractmethod
    async def execute_task(
        self,
        task_id: str,
        session_id: str,
        prompt: str,
        workspace_path: str,
        context: Optional[str] = None,
        is_continuation: bool = False,
    ) -> AsyncGenerator[AgentEvent, None]:
        """
        Execute prompt against the agent and stream events (tokens, tool calls, logs).
        Yields AgentEvent instances until execution finishes.
        """
        pass

    @abstractmethod
    async def cancel_task(self, task_id: str, session_id: Optional[str] = None) -> bool:
        """Cancel or abort a running task."""
        pass
