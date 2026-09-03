"""High-fidelity Simulated Agent Provider for testing and offline staging."""

import asyncio
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional
from app.providers.base import AgentEvent, BaseAgentProvider


class SimulatedAgentProvider(BaseAgentProvider):
    """
    High-fidelity simulated agent provider.
    Generates realistic thought processes, tool calls, and structured diffs
    without requiring external binaries or network credentials.
    """

    provider_id: str = "simulated"
    display_name: str = "Simulation Sandbox (Testing & Staging)"

    def __init__(self, step_delay: float = 0.2):
        self.step_delay = step_delay
        self._cancelled_tasks = set()

    async def check_health(self) -> Dict[str, Any]:
        return {
            "status": "connected",
            "provider": "simulated",
            "message": "Simulation provider operational.",
            "latency_ms": 0.5,
        }

    async def create_session(self, workspace_path: str, session_id: Optional[str] = None) -> str:
        return session_id or f"sim_sess_{uuid.uuid4().hex[:12]}"

    async def execute_task(
        self,
        task_id: str,
        session_id: str,
        prompt: str,
        workspace_path: str,
        context: Optional[str] = None,
        is_continuation: bool = False,
    ) -> AsyncGenerator[AgentEvent, None]:
        if task_id in self._cancelled_tasks:
            yield AgentEvent(event_type="status", message="Task already cancelled.", level="warning")
            return

        # 1. Thought analysis
        yield AgentEvent(
            event_type="thought",
            message=f"Received prompt from ChatGPT: '{prompt[:120]}...'. Parsing requirements and project context.",
            level="info",
            step_index=1,
        )
        effective_delay = 0.4 if "long running" in prompt.lower() else self.step_delay
        await asyncio.sleep(effective_delay)

        if task_id in self._cancelled_tasks:
            yield AgentEvent(event_type="status", message="Task cancelled.", level="warning")
            return

        # 2. Tool call: Project analysis
        yield AgentEvent(
            event_type="tool_call",
            message="Scanning repository files and configuration...",
            tool_name="read_project_context",
            tool_input={"workspace_path": workspace_path, "query": prompt[:50]},
            step_index=2,
        )
        await asyncio.sleep(self.step_delay)

        # 3. Tool call: File modification / creation
        file_path = "src/feature.py" if "auth" not in prompt.lower() else "src/auth/service.py"
        yield AgentEvent(
            event_type="tool_call",
            message=f"Applying code modifications to {file_path}...",
            tool_name="write_to_file",
            tool_input={
                "target_file": file_path,
                "description": f"Implemented requirements for: {prompt[:60]}",
            },
            step_index=3,
        )
        await asyncio.sleep(self.step_delay)

        # 4. Final response token stream
        result_message = (
            f"✅ Task executed successfully in session {session_id}.\n\n"
            f"**Implemented:**\n"
            f"- Addressed architect prompt: *{prompt}*\n"
            f"- Updated `{file_path}` with production-ready implementation.\n"
            f"- Validated syntax and ensured security best practices.\n"
            f"- Ready for continuation or review."
        )

        yield AgentEvent(
            event_type="token",
            message=result_message,
            level="info",
            step_index=4,
        )

        yield AgentEvent(
            event_type="status",
            message="Completed execution.",
            level="info",
            step_index=5,
        )

    async def cancel_task(self, task_id: str, session_id: Optional[str] = None) -> bool:
        self._cancelled_tasks.add(task_id)
        return True
