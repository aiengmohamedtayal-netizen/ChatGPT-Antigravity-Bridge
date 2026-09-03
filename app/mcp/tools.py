"""Model Context Protocol (MCP) Tools for ChatGPT Control Plane and Antigravity."""

import json
import logging
import os
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from app import database
from app.models.project import Project
from app.models.task import Task, ExecutionLog, TaskStatus, TaskPriority
from app.mcp.protocol import McpTool, McpToolInputSchema, McpToolResult, McpContentItem
from app.security.boundary import boundary_guard
from app.orchestration.context_manager import context_manager
from app.orchestration.orchestrator import orchestrator
from app.providers.registry import provider_registry

logger = logging.getLogger(__name__)

# =====================================================================
# CHATGPT CONTROL PLANE MCP TOOLS (ChatGPT -> Bridge -> Antigravity)
# =====================================================================

CHATGPT_CONTROL_TOOLS: List[McpTool] = [
    McpTool(
        name="list_projects",
        description="List all explicitly authorized Antigravity project workspaces available to ChatGPT.",
        inputSchema=McpToolInputSchema(
            properties={
                "enabled_only": {"type": "boolean", "default": True, "description": "Filter only active projects"},
            },
        ),
    ),
    McpTool(
        name="get_project",
        description="Retrieve metadata, status, and active sessions for a specific authorized project.",
        inputSchema=McpToolInputSchema(
            properties={
                "project_id": {"type": "string", "description": "Target Project ID"},
            },
            required=["project_id"],
        ),
    ),
    McpTool(
        name="get_project_context",
        description="Inspect codebase context, architecture guidelines (AGENTS.md), and tracked files for a project.",
        inputSchema=McpToolInputSchema(
            properties={
                "project_id": {"type": "string", "description": "Target Project ID"},
            },
            required=["project_id"],
        ),
    ),
    McpTool(
        name="get_project_tree",
        description="Retrieve a bounded, security-controlled file directory tree within the authorized workspace.",
        inputSchema=McpToolInputSchema(
            properties={
                "project_id": {"type": "string", "description": "Target Project ID"},
                "subpath": {"type": "string", "default": "", "description": "Optional subfolder relative to workspace root"},
                "max_depth": {"type": "integer", "default": 2, "description": "Max recursion depth (1-4)"},
            },
            required=["project_id"],
        ),
    ),
    McpTool(
        name="list_agent_sessions",
        description="List all active or past Antigravity Agent conversational sessions for a project.",
        inputSchema=McpToolInputSchema(
            properties={
                "project_id": {"type": "string", "description": "Target Project ID"},
            },
            required=["project_id"],
        ),
    ),
    McpTool(
        name="create_agent_session",
        description="Initialize a new real Antigravity Agent session for an authorized project.",
        inputSchema=McpToolInputSchema(
            properties={
                "project_id": {"type": "string", "description": "Target Project ID"},
                "title": {"type": "string", "description": "Optional session title"},
            },
            required=["project_id"],
        ),
    ),
    McpTool(
        name="send_agent_command",
        description="Primary Tool: Dispatch a real coding, inspection, or refactoring prompt to the Antigravity Agent.",
        inputSchema=McpToolInputSchema(
            properties={
                "project_id": {"type": "string", "description": "Target Project ID"},
                "prompt": {"type": "string", "description": "Instruction or task for Antigravity Agent"},
                "session_id": {"type": "string", "description": "Optional session ID to reuse an existing conversation"},
                "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"], "default": "normal"},
            },
            required=["project_id", "prompt"],
        ),
    ),
    McpTool(
        name="continue_agent_session",
        description="Send a follow-up instruction to the SAME Antigravity Agent session, preserving context.",
        inputSchema=McpToolInputSchema(
            properties={
                "session_id": {"type": "string", "description": "Active Antigravity Session ID to continue"},
                "prompt": {"type": "string", "description": "Follow-up instruction for the agent"},
                "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"], "default": "normal"},
            },
            required=["session_id", "prompt"],
        ),
    ),
    McpTool(
        name="get_agent_session",
        description="Retrieve details and task history for an Antigravity Agent session.",
        inputSchema=McpToolInputSchema(
            properties={
                "session_id": {"type": "string", "description": "Target Session ID"},
            },
            required=["session_id"],
        ),
    ),
    McpTool(
        name="get_task_status",
        description="Query the real-time execution status, summary, and modified files for a task.",
        inputSchema=McpToolInputSchema(
            properties={
                "task_id": {"type": "string", "description": "Task ID"},
            },
            required=["task_id"],
        ),
    ),
    McpTool(
        name="get_task_events",
        description="Fetch legitimate execution telemetry and tool call events for a task (private thoughts masked).",
        inputSchema=McpToolInputSchema(
            properties={
                "task_id": {"type": "string", "description": "Task ID"},
                "limit": {"type": "integer", "default": 50},
            },
            required=["task_id"],
        ),
    ),
    McpTool(
        name="cancel_agent_session",
        description="Cancel a running task or agent session in Antigravity.",
        inputSchema=McpToolInputSchema(
            properties={
                "session_id": {"type": "string", "description": "Session ID or Task ID to cancel"},
            },
            required=["session_id"],
        ),
    ),
    McpTool(
        name="get_system_status",
        description="Check Bridge connection health and active Antigravity Agent status.",
        inputSchema=McpToolInputSchema(properties={}),
    ),
]

# =====================================================================
# REVERSE TOOLS (Antigravity -> Bridge)
# =====================================================================

ANTIGRAVITY_BRIDGE_TOOLS: List[McpTool] = [
    McpTool(
        name="bridge_get_project_context",
        description="Retrieve repository context, system instructions, and file trees managed by the Bridge.",
        inputSchema=McpToolInputSchema(
            properties={
                "project_id": {"type": "string", "description": "Target Project ID"},
            },
            required=["project_id"],
        ),
    ),
    McpTool(
        name="bridge_report_task_progress",
        description="Emit a real-time progress update or tool execution status to the Bridge and ChatGPT.",
        inputSchema=McpToolInputSchema(
            properties={
                "task_id": {"type": "string", "description": "Active Task ID"},
                "level": {"type": "string", "enum": ["info", "warning", "tool_call", "thought"], "default": "info"},
                "message": {"type": "string", "description": "Progress description"},
                "tool_name": {"type": "string", "description": "Optional name of tool being executed"},
            },
            required=["task_id", "message"],
        ),
    ),
    McpTool(
        name="bridge_store_task_artifact",
        description="Store generated code artifacts, test logs, or build output for a task.",
        inputSchema=McpToolInputSchema(
            properties={
                "task_id": {"type": "string", "description": "Target Task ID"},
                "filename": {"type": "string", "description": "Artifact filename"},
                "content": {"type": "string", "description": "Artifact content"},
                "mime_type": {"type": "string", "default": "text/plain"},
            },
            required=["task_id", "filename", "content"],
        ),
    ),
]

# Combined tools list exposed over MCP
MCP_TOOLS: List[McpTool] = CHATGPT_CONTROL_TOOLS + ANTIGRAVITY_BRIDGE_TOOLS


# =====================================================================
# TOOL EXECUTION DISPATCHER
# =====================================================================

async def execute_mcp_tool(name: str, arguments: Dict[str, Any], db: Optional[Session] = None) -> McpToolResult:
    """Dispatch and execute an MCP tool with security validation."""
    should_close = False
    if db is None:
        db = database.SessionLocal()
        should_close = True

    try:
        # 1. list_projects
        if name == "list_projects":
            projects = db.query(Project).all()
            data = [
                {
                    "project_id": p.id,
                    "name": p.name,
                    "workspace_path": p.workspace_path,
                    "description": p.description,
                    "status": "authorized",
                    "active_sessions": [
                        s[0]
                        for s in db.query(Task.session_id)
                        .filter(Task.project_id == p.id, Task.session_id.isnot(None))
                        .distinct()
                        .all()
                        if s[0]
                    ],
                    "capabilities": ["inspect", "code_edit", "execute_agent", "continue_session"],
                }
                for p in projects
            ]
            return McpToolResult(content=[McpContentItem(text=json.dumps(data, indent=2))])

        # 2. get_project
        elif name == "get_project":
            proj_id = arguments.get("project_id", "")
            project = db.query(Project).filter(Project.id == proj_id).first()
            if not project:
                return McpToolResult(content=[McpContentItem(text=f"Error: Project '{proj_id}' not found.")], isError=True)

            active_sessions = [
                s[0]
                for s in db.query(Task.session_id)
                .filter(Task.project_id == project.id, Task.session_id.isnot(None))
                .distinct()
                .all()
                if s[0]
            ]

            info = {
                "project_id": project.id,
                "name": project.name,
                "workspace_path": project.workspace_path,
                "description": project.description,
                "status": "authorized",
                "active_sessions": active_sessions,
                "created_at": project.created_at.isoformat() if project.created_at else None,
            }
            return McpToolResult(content=[McpContentItem(text=json.dumps(info, indent=2))])

        # 3. get_project_context
        elif name in ("get_project_context", "bridge_get_project_context"):
            proj_id = arguments.get("project_id", "")
            project = db.query(Project).filter(Project.id == proj_id).first()
            if not project:
                return McpToolResult(content=[McpContentItem(text=f"Error: Project '{proj_id}' not found.")], isError=True)

            scan = context_manager.inspect_workspace(project.workspace_path)
            context = {
                "project_id": project.id,
                "name": project.name,
                "workspace_path": project.workspace_path,
                "instructions": project.instructions or scan.get("discovered_instructions", ""),
                "exists_on_disk": scan.get("exists", False),
                "tracked_files_count": scan.get("files_count", 0),
                "sample_files": scan.get("summary", [])[:20],
            }
            return McpToolResult(content=[McpContentItem(text=json.dumps(context, indent=2))])

        # 4. get_project_tree
        elif name == "get_project_tree":
            proj_id = arguments.get("project_id", "")
            subpath = arguments.get("subpath", "")
            max_depth = min(max(int(arguments.get("max_depth", 2)), 1), 4)

            project = db.query(Project).filter(Project.id == proj_id).first()
            if not project:
                return McpToolResult(content=[McpContentItem(text=f"Error: Project '{proj_id}' not found.")], isError=True)

            # Enforce boundary security (blocks traversal / unauthorized files)
            safe_target = boundary_guard.sanitize_relative_subpath(subpath, project.workspace_path)

            tree = []
            base_depth = safe_target.rstrip(os.sep).count(os.sep)
            for root, dirs, files in os.walk(safe_target):
                dirs[:] = [d for d in dirs if d not in {".git", "node_modules", ".venv", "__pycache__", "dist", "build"}]
                cur_depth = root.count(os.sep) - base_depth
                if cur_depth > max_depth:
                    continue

                rel_dir = os.path.relpath(root, safe_target)
                for f in files:
                    rel_file = os.path.normpath(os.path.join(rel_dir, f)) if rel_dir != "." else f
                    tree.append(rel_file)
                    if len(tree) >= 100:
                        break
                if len(tree) >= 100:
                    break

            return McpToolResult(content=[McpContentItem(text=json.dumps({"root": subpath or "/", "files": tree}, indent=2))])

        # 5. list_agent_sessions
        elif name == "list_agent_sessions":
            proj_id = arguments.get("project_id", "")
            sessions = (
                db.query(Task.session_id)
                .filter(Task.project_id == proj_id, Task.session_id.isnot(None))
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
                    "last_prompt": last_task.prompt[:80] if last_task else "",
                    "last_status": last_task.status if last_task else "",
                    "updated_at": last_task.created_at.isoformat() if last_task and last_task.created_at else None,
                })
            return McpToolResult(content=[McpContentItem(text=json.dumps(data, indent=2))])

        # 6. create_agent_session
        elif name == "create_agent_session":
            proj_id = arguments.get("project_id", "")
            project = db.query(Project).filter(Project.id == proj_id).first()
            if not project:
                return McpToolResult(content=[McpContentItem(text=f"Error: Project '{proj_id}' not found.")], isError=True)

            provider = provider_registry.get_provider()
            session_id = await provider.create_session(workspace_path=project.workspace_path)

            return McpToolResult(content=[McpContentItem(text=json.dumps({
                "session_id": session_id,
                "project_id": project.id,
                "status": "initialized",
                "message": f"Real Antigravity session created for '{project.name}'.",
            }, indent=2))])

        # 7. send_agent_command (PRIMARY TOOL)
        elif name == "send_agent_command":
            proj_id = arguments.get("project_id", "")
            prompt = arguments.get("prompt", "")
            session_id = arguments.get("session_id")
            priority = arguments.get("priority", TaskPriority.NORMAL)

            project = db.query(Project).filter(Project.id == proj_id).first()
            if not project:
                return McpToolResult(content=[McpContentItem(text=f"Error: Project '{proj_id}' not found.")], isError=True)

            # Create task record
            task = Task(
                project_id=project.id,
                session_id=session_id,
                prompt=prompt,
                priority=priority,
                status=TaskStatus.QUEUED,
            )
            db.add(task)
            db.commit()
            db.refresh(task)

            # Enqueue in orchestrator
            await orchestrator.enqueue_task(task.id, task.priority)

            return McpToolResult(content=[McpContentItem(text=json.dumps({
                "task_id": task.id,
                "project_id": project.id,
                "session_id": session_id or "auto-resolving",
                "status": "queued",
                "message": "Instruction dispatched to Antigravity Agent.",
            }, indent=2))])

        # 8. continue_agent_session
        elif name == "continue_agent_session":
            session_id = arguments.get("session_id", "")
            prompt = arguments.get("prompt", "")
            priority = arguments.get("priority", TaskPriority.NORMAL)

            # Find latest task in this session
            parent = (
                db.query(Task)
                .filter(Task.session_id == session_id)
                .order_by(Task.created_at.desc())
                .first()
            )
            if not parent:
                return McpToolResult(content=[McpContentItem(text=f"Error: Session '{session_id}' not found.")], isError=True)

            child = Task(
                project_id=parent.project_id,
                parent_task_id=parent.id,
                session_id=session_id,
                prompt=prompt,
                priority=priority,
                status=TaskStatus.QUEUED,
            )
            db.add(child)
            db.commit()
            db.refresh(child)

            await orchestrator.enqueue_task(child.id, child.priority)

            return McpToolResult(content=[McpContentItem(text=json.dumps({
                "task_id": child.id,
                "parent_task_id": parent.id,
                "session_id": session_id,
                "status": "queued",
                "message": "Follow-up instruction attached to existing Antigravity session.",
            }, indent=2))])

        # 9. get_agent_session
        elif name == "get_agent_session":
            session_id = arguments.get("session_id", "")
            tasks = (
                db.query(Task)
                .filter(Task.session_id == session_id)
                .order_by(Task.created_at.asc())
                .all()
            )
            if not tasks:
                return McpToolResult(content=[McpContentItem(text=f"Session '{session_id}' not found.")], isError=True)

            data = {
                "session_id": session_id,
                "project_id": tasks[0].project_id,
                "total_tasks": len(tasks),
                "history": [
                    {
                        "task_id": t.id,
                        "prompt": t.prompt,
                        "status": t.status,
                        "summary": (t.antigravity_response or {}).get("summary", ""),
                        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
                    }
                    for t in tasks
                ],
            }
            return McpToolResult(content=[McpContentItem(text=json.dumps(data, indent=2))])

        # 10. get_task_status
        elif name == "get_task_status":
            task_id = arguments.get("task_id", "")
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                return McpToolResult(content=[McpContentItem(text=f"Task '{task_id}' not found.")], isError=True)

            resp = {
                "task_id": task.id,
                "project_id": task.project_id,
                "session_id": task.session_id,
                "status": task.status,
                "prompt": task.prompt,
                "summary": (task.antigravity_response or {}).get("summary", ""),
                "files_changed": (task.antigravity_response or {}).get("files_modified", []),
                "artifacts": (task.antigravity_response or {}).get("artifacts", []),
                "error": task.error_info,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            }
            return McpToolResult(content=[McpContentItem(text=json.dumps(resp, indent=2))])

        # 11. get_task_events (masks private reasoning)
        elif name == "get_task_events":
            task_id = arguments.get("task_id", "")
            limit = min(int(arguments.get("limit", 50)), 100)
            logs = (
                db.query(ExecutionLog)
                .filter(ExecutionLog.task_id == task_id)
                .order_by(ExecutionLog.id.asc())
                .limit(limit)
                .all()
            )
            # Filter out internal thoughts/signatures for clean developer observability
            events = [
                {
                    "step": l.step_index,
                    "timestamp": l.timestamp.isoformat() if l.timestamp else None,
                    "level": l.level,
                    "event": l.message,
                    "tool": l.tool_name,
                }
                for l in logs
                if l.level != "thought"
            ]
            return McpToolResult(content=[McpContentItem(text=json.dumps(events, indent=2))])

        # 12. cancel_agent_session
        elif name == "cancel_agent_session":
            target = arguments.get("session_id", "")
            # Try task_id first
            success = await orchestrator.cancel_task(target)
            if not success:
                # If target is session_id, cancel running task in that session
                task = db.query(Task).filter(Task.session_id == target, Task.status == TaskStatus.RUNNING).first()
                if task:
                    success = await orchestrator.cancel_task(task.id)

            return McpToolResult(content=[McpContentItem(text=json.dumps({"success": success, "target": target}))])

        # 13. get_system_status
        elif name == "get_system_status":
            provider = provider_registry.get_provider()
            health = await provider.check_health()
            return McpToolResult(content=[McpContentItem(text=json.dumps({
                "provider": provider.display_name,
                "status": health.get("status"),
                "latency_ms": health.get("latency_ms"),
                "details": health.get("message"),
            }, indent=2))])

        # Reverse tools (bridge_report_task_progress, bridge_store_task_artifact)
        elif name == "bridge_report_task_progress":
            task_id = arguments.get("task_id", "")
            message = arguments.get("message", "")
            level = arguments.get("level", "info")
            tool_name = arguments.get("tool_name")
            log_entry = ExecutionLog(task_id=task_id, level=level, message=message, tool_name=tool_name)
            db.add(log_entry)
            db.commit()
            return McpToolResult(content=[McpContentItem(text="Progress logged.")])

        elif name == "bridge_store_task_artifact":
            task_id = arguments.get("task_id", "")
            filename = arguments.get("filename", "artifact.txt")
            content = arguments.get("content", "")
            task = db.query(Task).filter(Task.id == task_id).first()
            if task:
                resp = dict(task.antigravity_response or {})
                artifacts = resp.get("artifacts", [])
                artifacts.append({"filename": filename, "size": len(content)})
                resp["artifacts"] = artifacts
                task.antigravity_response = resp
                db.commit()
            return McpToolResult(content=[McpContentItem(text="Artifact stored.")])

        else:
            return McpToolResult(content=[McpContentItem(text=f"Unknown tool: '{name}'.")], isError=True)

    except Exception as e:
        logger.error("Error executing MCP tool %s: %s", name, e, exc_info=True)
        return McpToolResult(content=[McpContentItem(text=f"Error: {str(e)}")], isError=True)
    finally:
        if should_close:
            db.close()
