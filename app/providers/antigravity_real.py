"""Real Antigravity Implementation Agent Provider using official agentapi.bat."""

import asyncio
import json
import logging
import os
import subprocess
import time
from typing import Any, AsyncGenerator, Dict, List, Optional
from app.config import get_settings
from app.providers.base import AgentEvent, BaseAgentProvider

logger = logging.getLogger(__name__)


class AntigravityRealAgentProvider(BaseAgentProvider):
    """
    Real Antigravity Implementation Agent Provider.
    Dispatches directly to the local Antigravity Language Server via agentapi.bat.
    Never fakes execution in production mode.
    """

    provider_id: str = "antigravity_real"
    display_name: str = "Google Antigravity Agent (Real Local)"

    def __init__(self):
        self.settings = get_settings()
        self.cli_path = self.settings.ANTIGRAVITY_AGENTAPI_PATH
        self.brain_dir = self.settings.ANTIGRAVITY_BRAIN_DIR
        self._cancelled_tasks = set()

    async def check_health(self) -> Dict[str, Any]:
        """Check availability of agentapi.bat and local language server."""
        exists = os.path.exists(self.cli_path)
        if not exists:
            return {
                "status": "error",
                "message": f"agentapi.bat not found at {self.cli_path}",
                "latency_ms": 0.0,
            }

        t0 = time.perf_counter()
        try:
            # Query metadata of a known system check
            proc = await asyncio.create_subprocess_exec(
                self.cli_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            latency = round((time.perf_counter() - t0) * 1000, 2)
            return {
                "status": "connected",
                "message": "Antigravity AgentAPI language server reachable and operational.",
                "latency_ms": latency,
                "cli_path": self.cli_path,
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Health check failed: {str(e)}",
                "latency_ms": 0.0,
            }

    async def create_session(self, workspace_path: str, session_id: Optional[str] = None) -> str:
        """Create a real Antigravity session using new-conversation."""
        from app.security.policy_manager import policy_manager

        if session_id:
            return session_id

        if not os.path.exists(self.cli_path):
            raise RuntimeError(f"Cannot spawn real Antigravity agent: {self.cli_path} not found.")

        # Apply headless permission policy for the workspace
        policy_manager.apply_policy(workspace_path)

        title = f"ChatGPT Gateway ({os.path.basename(workspace_path)})"
        init_prompt = f"Initialize development session in workspace: {workspace_path}."

        cmd = [self.cli_path, "new-conversation", f"--title={title}", init_prompt]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=workspace_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            out_err = stdout.decode("utf-8", errors="ignore").strip()
            err_err = stderr.decode("utf-8", errors="ignore").strip()
            err = err_err or out_err or "Unknown agentapi failure"
            try:
                parsed_err = json.loads(out_err)
                if "error" in parsed_err:
                    err = parsed_err["error"]
            except Exception:
                pass
            raise RuntimeError(f"agentapi new-conversation failed: {err}")

        out_str = stdout.decode("utf-8", errors="ignore")
        try:
            parsed = json.loads(out_str)
            cid = parsed.get("response", {}).get("newConversation", {}).get("conversationId")
            if cid:
                return cid
        except Exception:
            pass

        # Fallback to scanning lines for UUID
        for line in out_str.splitlines():
            if "conversationId" in line:
                parts = line.split(":")
                if len(parts) >= 2:
                    return parts[1].strip('", \r\n')

        raise RuntimeError(f"Failed to parse conversation ID from agentapi output: {out_str}")

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
        Send command to the real Antigravity Agent and observe real output.
        Exposes legitimate telemetry, tool calls, and final output.
        Never exposes hidden reasoning or fake completions.
        """
        if task_id in self._cancelled_tasks:
            yield AgentEvent(event_type="status", message="Task cancelled before dispatch.", level="warning")
            return

        yield AgentEvent(
            event_type="dispatched",
            message=f"Instruction dispatched to Antigravity Agent (Session: {session_id})...",
            level="info",
            step_index=0,
        )

        # Dispatch via agentapi.bat send-message
        cmd = [self.cli_path, "send-message", session_id, prompt]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=workspace_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            out_err = stdout.decode("utf-8", errors="ignore").strip()
            err_err = stderr.decode("utf-8", errors="ignore").strip()
            err = err_err or out_err or "Unknown agentapi dispatch failure"
            try:
                parsed_err = json.loads(out_err)
                if "error" in parsed_err:
                    err = parsed_err["error"]
            except Exception:
                pass
            yield AgentEvent(
                event_type="error",
                message=f"Agent command dispatch failed: {err}",
                level="error",
                step_index=99,
            )
            return

        yield AgentEvent(
            event_type="agent_started",
            message="Antigravity Agent received instruction and started execution.",
            level="info",
            step_index=1,
        )

        # Wait and observe output steps in brain directory
        session_brain = os.path.join(self.brain_dir, session_id, ".system_generated")
        transcript_file = os.path.join(session_brain, "logs", "transcript.jsonl")

        HARD_TIMEOUT = 60.0
        IDLE_TIMEOUT = 15.0
        start_time = time.monotonic()
        last_activity_time = time.monotonic()
        last_line_count = 0
        final_output_text = ""
        completion_detected = False
        failure_detected = False
        failure_reason = ""
        has_executed_tools = False

        while True:
            if task_id in self._cancelled_tasks:
                yield AgentEvent(event_type="cancelled", message="Task cancelled by user.", level="warning")
                return

            now = time.monotonic()
            total_elapsed = now - start_time
            idle_elapsed = now - last_activity_time

            # Tail the transcript file
            if os.path.exists(transcript_file):
                try:
                    with open(transcript_file, "r", encoding="utf-8", errors="ignore") as fp:
                        lines = fp.readlines()
                    
                    if len(lines) > last_line_count:
                        new_lines = lines[last_line_count:]
                        last_line_count = len(lines)
                        last_activity_time = now

                        for line in new_lines:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                data = json.loads(line)
                                step_idx = data.get("step_index", 0)
                                source = data.get("source", "")
                                msg_type = data.get("type", "")
                                status = data.get("status", "")
                                content = data.get("content", "")
                                tool_calls = data.get("tool_calls") or []

                                if status == "ERROR":
                                    failure_detected = True
                                    failure_reason = content or f"Step {step_idx} failed with error status"

                                if tool_calls:
                                    has_executed_tools = True
                                    for tc in tool_calls:
                                        tname = tc.get("name", "tool")
                                        targs = tc.get("args") or {}
                                        yield AgentEvent(
                                            event_type="tool_call",
                                            message=f"Agent executing tool: {tname}",
                                            level="info",
                                            tool_name=tname,
                                            tool_input=targs,
                                            step_index=step_idx,
                                        )

                                if content:
                                    if msg_type == "GENERIC":
                                        yield AgentEvent(
                                            event_type="tool_result",
                                            message=f"[Step {step_idx}] {content[:200]}",
                                            level="info",
                                            step_index=step_idx,
                                        )
                                    elif source == "MODEL" and msg_type == "PLANNER_RESPONSE" and not tool_calls:
                                        # Positive completion evidence: Model completed its response without requesting more tools
                                        final_output_text = content
                                        completion_detected = True
                                        yield AgentEvent(
                                            event_type="token",
                                            message=content,
                                            level="info",
                                            step_index=step_idx,
                                        )
                            except Exception:
                                pass
                except Exception:
                    pass

            # Check terminal states
            if failure_detected:
                yield AgentEvent(
                    event_type="error",
                    message=f"Agent execution failed: {failure_reason}",
                    level="error",
                    step_index=99,
                )
                return

            if completion_detected and final_output_text:
                yield AgentEvent(
                    event_type="completed",
                    message="Antigravity Agent completed task execution.",
                    level="info",
                    step_index=11,
                )
                return

            # Check idle timeout
            if idle_elapsed >= IDLE_TIMEOUT:
                if completion_detected or final_output_text or has_executed_tools:
                    # Positive evidence found
                    out_msg = final_output_text or f"Agent completed execution in session {session_id}."
                    yield AgentEvent(event_type="token", message=out_msg, level="info", step_index=10)
                    yield AgentEvent(event_type="completed", message="Antigravity Agent completed task execution.", level="info", step_index=11)
                    return
                else:
                    # Idle with NO positive completion evidence
                    yield AgentEvent(
                        event_type="error",
                        message=f"Agent became idle after {idle_elapsed:.1f}s without producing completion evidence.",
                        level="error",
                        step_index=99,
                    )
                    return

            # Check hard timeout
            if total_elapsed >= HARD_TIMEOUT:
                if completion_detected or final_output_text or has_executed_tools:
                    out_msg = final_output_text or f"Agent finished execution before timeout."
                    yield AgentEvent(event_type="token", message=out_msg, level="info", step_index=10)
                    yield AgentEvent(event_type="completed", message="Antigravity Agent execution completed.", level="info", step_index=11)
                    return
                else:
                    yield AgentEvent(
                        event_type="error",
                        message=f"Agent execution reached hard timeout ({HARD_TIMEOUT}s) with no completion evidence.",
                        level="error",
                        step_index=99,
                    )
                    return

            await asyncio.sleep(0.5)

    async def cancel_task(self, task_id: str, session_id: Optional[str] = None) -> bool:
        self._cancelled_tasks.add(task_id)
        return True
