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
from app.services.workspace_service import workspace_service
from app.services.fs_service import fs_service
from app.core.errors import BridgeException

logger = logging.getLogger(__name__)

# =====================================================================
# DYNAMIC WORKSPACE & FILESYSTEM MCP TOOLS
# =====================================================================

WORKSPACE_FILESYSTEM_TOOLS: List[McpTool] = [
    McpTool(
        name="list_workspaces",
        description="List all explicitly authorized workspace roots available to ChatGPT (e.g. tool, training, smart home).",
        inputSchema=McpToolInputSchema(
            properties={
                "enabled_only": {
                    "type": "boolean",
                    "default": True,
                    "description": "Filter only enabled workspaces",
                },
            },
        ),
    ),
    McpTool(
        name="get_workspace",
        description="Retrieve metadata, status, disk existence, and preview entries for a specific authorized workspace.",
        inputSchema=McpToolInputSchema(
            properties={
                "workspace_id": {
                    "type": "string",
                    "description": "Authorized Workspace ID or canonical path (e.g. 'proj_smart_home', 'proj_tool')",
                },
            },
            required=["workspace_id"],
        ),
    ),
    McpTool(
        name="list_directory",
        description="List files and directories inside an authorized workspace root or subfolder with metadata.",
        inputSchema=McpToolInputSchema(
            properties={
                "path": {
                    "type": "string",
                    "description": "Absolute path or relative subpath within an authorized workspace",
                },
                "workspace_id": {
                    "type": "string",
                    "description": "Optional Workspace ID to scope the listing (e.g. 'proj_smart_home')",
                },
                "show_hidden": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whether to include hidden files (starting with .)",
                },
            },
        ),
    ),
    McpTool(
        name="read_file",
        description="Safely read the text content of a file located within an authorized workspace.",
        inputSchema=McpToolInputSchema(
            properties={
                "path": {
                    "type": "string",
                    "description": "Absolute path or relative path to the file within an authorized workspace",
                },
                "workspace_id": {
                    "type": "string",
                    "description": "Optional Workspace ID scoping the target file",
                },
                "max_bytes": {
                    "type": "integer",
                    "default": 1000000,
                    "description": "Maximum bytes to read (default 1MB)",
                },
                "offset": {
                    "type": "integer",
                    "default": 0,
                    "description": "Byte offset from which to start reading",
                },
            },
            required=["path"],
        ),
    ),
    McpTool(
        name="write_file",
        description="Safely create or overwrite a file within an authorized workspace (parent folders auto-created).",
        inputSchema=McpToolInputSchema(
            properties={
                "path": {
                    "type": "string",
                    "description": "Absolute or relative path of the file to create or update",
                },
                "content": {
                    "type": "string",
                    "description": "UTF-8 string content to write into the file",
                },
                "workspace_id": {
                    "type": "string",
                    "description": "Optional Workspace ID scoping the target file",
                },
                "overwrite": {
                    "type": "boolean",
                    "default": True,
                    "description": "Allow overwriting if the file already exists",
                },
            },
            required=["path", "content"],
        ),
    ),
    McpTool(
        name="create_directory",
        description="Safely create a directory within an authorized workspace (mkdir -p behavior).",
        inputSchema=McpToolInputSchema(
            properties={
                "path": {
                    "type": "string",
                    "description": "Directory path to create within an authorized workspace",
                },
                "workspace_id": {
                    "type": "string",
                    "description": "Optional Workspace ID scoping the target folder",
                },
            },
            required=["path"],
        ),
    ),
    McpTool(
        name="move_file",
        description="Rename or move a file/folder between authorized paths.",
        inputSchema=McpToolInputSchema(
            properties={
                "source_path": {
                    "type": "string",
                    "description": "Source path of the file or directory to move",
                },
                "target_path": {
                    "type": "string",
                    "description": "Destination path within an authorized workspace",
                },
                "workspace_id": {
                    "type": "string",
                    "description": "Optional Workspace ID scoping the operation",
                },
                "overwrite": {
                    "type": "boolean",
                    "default": False,
                    "description": "Allow overwriting destination if it already exists",
                },
            },
            required=["source_path", "target_path"],
        ),
    ),
    McpTool(
        name="delete_file",
        description="Safely delete a file or directory within an authorized workspace. Requires explicit confirm=True.",
        inputSchema=McpToolInputSchema(
            properties={
                "path": {
                    "type": "string",
                    "description": "Path to the file or directory to delete",
                },
                "workspace_id": {
                    "type": "string",
                    "description": "Optional Workspace ID scoping the target",
                },
                "recursive": {
                    "type": "boolean",
                    "default": False,
                    "description": "Delete non-empty directories recursively",
                },
                "confirm": {
                    "type": "boolean",
                    "default": False,
                    "description": "Explicit confirmation flag required to prevent accidental data loss",
                },
            },
            required=["path", "confirm"],
        ),
    ),
    McpTool(
        name="search_files",
        description="Search files in authorized workspaces by filename/glob pattern or text content.",
        inputSchema=McpToolInputSchema(
            properties={
                "query": {
                    "type": "string",
                    "description": "Search pattern (e.g. '*.ts', 'package.json') or text substring",
                },
                "workspace_id": {
                    "type": "string",
                    "description": "Optional Workspace ID to scope search (if omitted, searches all authorized roots)",
                },
                "search_type": {
                    "type": "string",
                    "enum": ["filename", "content"],
                    "default": "filename",
                    "description": "Type of search: 'filename' (name/glob) or 'content' (text in files)",
                },
                "max_results": {
                    "type": "integer",
                    "default": 50,
                    "description": "Maximum number of search matches to return",
                },
            },
            required=["query"],
        ),
    ),
    McpTool(
        name="get_file_tree",
        description="Retrieve a bounded, security-controlled file directory tree within an authorized workspace.",
        inputSchema=McpToolInputSchema(
            properties={
                "workspace_id": {
                    "type": "string",
                    "description": "Optional Workspace ID (e.g. 'proj_smart_home', 'proj_tool')",
                },
                "path": {
                    "type": "string",
                    "description": "Optional folder path within authorized workspace to root the tree",
                },
                "max_depth": {
                    "type": "integer",
                    "default": 3,
                    "description": "Maximum directory recursion depth (1-5)",
                },
                "max_entries": {
                    "type": "integer",
                    "default": 200,
                    "description": "Maximum total tree nodes to inspect",
                },
            },
        ),
    ),
]

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
                "project_id": {"type": "string", "description": "Target Project ID or Workspace ID"},
            },
            required=["project_id"],
        ),
    ),
    McpTool(
        name="get_project_context",
        description="Inspect codebase context, architecture guidelines (AGENTS.md), and tracked files for a project.",
        inputSchema=McpToolInputSchema(
            properties={
                "project_id": {"type": "string", "description": "Target Project ID or Workspace ID"},
            },
            required=["project_id"],
        ),
    ),
    McpTool(
        name="get_project_tree",
        description="Retrieve a bounded, security-controlled file directory tree within the authorized workspace.",
        inputSchema=McpToolInputSchema(
            properties={
                "project_id": {"type": "string", "description": "Target Project ID or Workspace ID"},
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
                "project_id": {"type": "string", "description": "Target Project ID or Workspace ID"},
            },
            required=["project_id"],
        ),
    ),
    McpTool(
        name="create_agent_session",
        description="Initialize a new real Antigravity Agent session for an authorized workspace/project.",
        inputSchema=McpToolInputSchema(
            properties={
                "project_id": {"type": "string", "description": "Target Project ID or Workspace ID"},
                "workspace_id": {"type": "string", "description": "Alias for project_id"},
                "title": {"type": "string", "description": "Optional session title"},
            },
        ),
    ),
    McpTool(
        name="send_agent_command",
        description="Primary Tool: Dispatch a real coding, inspection, or refactoring prompt to the Antigravity Agent.",
        inputSchema=McpToolInputSchema(
            properties={
                "project_id": {"type": "string", "description": "Target Project ID or Workspace ID (e.g. 'proj_smart_home', 'proj_tool')"},
                "workspace_id": {"type": "string", "description": "Alias for project_id"},
                "prompt": {"type": "string", "description": "Instruction or task for Antigravity Agent"},
                "session_id": {"type": "string", "description": "Optional session ID to reuse an existing conversation"},
                "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"], "default": "normal"},
            },
            required=["prompt"],
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
MCP_TOOLS: List[McpTool] = WORKSPACE_FILESYSTEM_TOOLS + CHATGPT_CONTROL_TOOLS + ANTIGRAVITY_BRIDGE_TOOLS


# =====================================================================
# TOOL EXECUTION DISPATCHER
# =====================================================================

def _resolve_project(target_id: str, db: Session) -> Optional[Project]:
    """Resolve project by ID, workspace ID, or path, auto-syncing if needed."""
    if not target_id:
        # Default to first authorized workspace
        workspaces = workspace_service.list_authorized_workspaces(enabled_only=True)
        if workspaces:
            target_id = workspaces[0].id

    # 1. Direct project lookup
    proj = db.query(Project).filter(Project.id == target_id).first()
    if proj:
        return proj

    # 2. Check workspace service
    ws = workspace_service.get_workspace(target_id)
    if ws:
        workspace_service.sync_with_db(db)
        proj = db.query(Project).filter(Project.id == ws.id).first()
        if not proj:
            proj = db.query(Project).filter(Project.workspace_path == ws.path).first()
        return proj

    return None


async def execute_mcp_tool(name: str, arguments: Dict[str, Any], db: Optional[Session] = None) -> McpToolResult:
    """Dispatch and execute an MCP tool with security validation."""
    should_close = False
    if db is None:
        db = database.SessionLocal()
        should_close = True

    try:
        # ==========================================
        # Dynamic Filesystem Tools
        # ==========================================
        if name == "list_workspaces":
            enabled_only = arguments.get("enabled_only", True)
            res = fs_service.list_workspaces(enabled_only=enabled_only)
            return McpToolResult(content=[McpContentItem(text=json.dumps(res, indent=2))])

        elif name == "get_workspace":
            ws_id = arguments.get("workspace_id") or arguments.get("path", "")
            res = fs_service.get_workspace(ws_id)
            return McpToolResult(content=[McpContentItem(text=json.dumps(res, indent=2))])

        elif name == "list_directory":
            path = arguments.get("path")
            workspace_id = arguments.get("workspace_id")
            show_hidden = arguments.get("show_hidden", False)
            res = fs_service.list_directory(path=path, workspace_id=workspace_id, show_hidden=show_hidden)
            return McpToolResult(content=[McpContentItem(text=json.dumps(res, indent=2))])

        elif name == "read_file":
            path = arguments.get("path", "")
            workspace_id = arguments.get("workspace_id")
            max_bytes = int(arguments.get("max_bytes", 1_000_000))
            offset = int(arguments.get("offset", 0))
            res = fs_service.read_file(path=path, workspace_id=workspace_id, max_bytes=max_bytes, offset=offset)
            return McpToolResult(content=[McpContentItem(text=json.dumps(res, indent=2))])

        elif name == "write_file":
            path = arguments.get("path", "")
            content = arguments.get("content", "")
            workspace_id = arguments.get("workspace_id")
            overwrite = arguments.get("overwrite", True)
            res = fs_service.write_file(path=path, content=content, workspace_id=workspace_id, overwrite=overwrite)
            return McpToolResult(content=[McpContentItem(text=json.dumps(res, indent=2))])

        elif name == "create_directory":
            path = arguments.get("path", "")
            workspace_id = arguments.get("workspace_id")
            res = fs_service.create_directory(path=path, workspace_id=workspace_id)
            return McpToolResult(content=[McpContentItem(text=json.dumps(res, indent=2))])

        elif name == "move_file":
            src = arguments.get("source_path", "")
            dst = arguments.get("target_path", "")
            workspace_id = arguments.get("workspace_id")
            overwrite = arguments.get("overwrite", False)
            res = fs_service.move_file(src, dst, workspace_id=workspace_id, overwrite=overwrite)
            return McpToolResult(content=[McpContentItem(text=json.dumps(res, indent=2))])

        elif name == "delete_file":
            path = arguments.get("path", "")
            workspace_id = arguments.get("workspace_id")
            recursive = arguments.get("recursive", False)
            confirm = arguments.get("confirm", False)
            res = fs_service.delete_file(path, workspace_id=workspace_id, recursive=recursive, confirm=confirm)
            return McpToolResult(content=[McpContentItem(text=json.dumps(res, indent=2))])

        elif name == "search_files":
            query = arguments.get("query", "")
            workspace_id = arguments.get("workspace_id")
            search_type = arguments.get("search_type", "filename")
            max_results = int(arguments.get("max_results", 50))
            res = fs_service.search_files(query, workspace_id=workspace_id, search_type=search_type, max_results=max_results)
            return McpToolResult(content=[McpContentItem(text=json.dumps(res, indent=2))])

        elif name == "get_file_tree":
            workspace_id = arguments.get("workspace_id")
            path = arguments.get("path")
            max_depth = int(arguments.get("max_depth", 3))
            max_entries = int(arguments.get("max_entries", 200))
            res = fs_service.get_file_tree(path=path, workspace_id=workspace_id, max_depth=max_depth, max_entries=max_entries)
            return McpToolResult(content=[McpContentItem(text=json.dumps(res, indent=2))])

        # ==========================================
        # Projects & Control Plane Tools
        # ==========================================
        elif name == "list_projects":
            workspace_service.sync_with_db(db)
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

        elif name == "get_project":
            proj_id = arguments.get("project_id", "")
            project = _resolve_project(proj_id, db)
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

        elif name in ("get_project_context", "bridge_get_project_context"):
            proj_id = arguments.get("project_id", "")
            project = _resolve_project(proj_id, db)
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

        elif name == "get_project_tree":
            proj_id = arguments.get("project_id", "")
            subpath = arguments.get("subpath", "")
            max_depth = min(max(int(arguments.get("max_depth", 2)), 1), 4)

            project = _resolve_project(proj_id, db)
            if not project:
                return McpToolResult(content=[McpContentItem(text=f"Error: Project '{proj_id}' not found.")], isError=True)

            safe_target = boundary_guard.sanitize_relative_subpath(subpath, project.workspace_path)
            tree_data = fs_service.get_file_tree(path=safe_target, workspace_id=project.id, max_depth=max_depth)
            return McpToolResult(content=[McpContentItem(text=json.dumps(tree_data, indent=2))])

        elif name == "list_agent_sessions":
            proj_id = arguments.get("project_id", "")
            project = _resolve_project(proj_id, db)
            if not project:
                return McpToolResult(content=[McpContentItem(text=f"Error: Project '{proj_id}' not found.")], isError=True)

            tasks = (
                db.query(Task)
                .filter(Task.project_id == project.id, Task.session_id.isnot(None))
                .order_by(Task.created_at.desc())
                .all()
            )
            sessions_dict: Dict[str, Any] = {}
            for t in tasks:
                if t.session_id not in sessions_dict:
                    sessions_dict[t.session_id] = {
                        "session_id": t.session_id,
                        "project_id": project.id,
                        "first_prompt": t.prompt[:100],
                        "task_status": t.status,
                        "created_at": t.created_at.isoformat() if t.created_at else None,
                    }
            return McpToolResult(content=[McpContentItem(text=json.dumps(list(sessions_dict.values()), indent=2))])

        elif name == "create_agent_session":
            proj_id = arguments.get("project_id") or arguments.get("workspace_id", "")
            title = arguments.get("title")
            project = _resolve_project(proj_id, db)
            if not project:
                return McpToolResult(content=[McpContentItem(text=f"Error: Project '{proj_id}' not found.")], isError=True)

            provider = provider_registry.get_provider()
            session_id = await provider.create_session(workspace_path=project.workspace_path)

            task = Task(
                project_id=project.id,
                session_id=session_id,
                prompt=f"Initialize agent session: {title or 'Session Started'}",
                priority=TaskPriority.NORMAL,
                status=TaskStatus.COMPLETED,
            )
            db.add(task)
            db.commit()

            return McpToolResult(
                content=[
                    McpContentItem(
                        text=json.dumps({
                            "session_id": session_id,
                            "project_id": project.id,
                            "workspace_path": project.workspace_path,
                            "status": "ready",
                        }, indent=2)
                    )
                ]
            )

        elif name == "send_agent_command":
            proj_id = arguments.get("project_id") or arguments.get("workspace_id", "")
            prompt = arguments.get("prompt", "")
            session_id = arguments.get("session_id")
            priority = arguments.get("priority", TaskPriority.NORMAL)

            project = _resolve_project(proj_id, db)
            if not project:
                return McpToolResult(content=[McpContentItem(text=f"Error: Project/Workspace '{proj_id}' not found in authorized workspaces.")], isError=True)

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

            await orchestrator.enqueue_task(task.id, priority=priority)

            return McpToolResult(
                content=[
                    McpContentItem(
                        text=json.dumps({
                            "task_id": task.id,
                            "project_id": project.id,
                            "workspace_path": project.workspace_path,
                            "session_id": session_id,
                            "status": "queued",
                            "message": f"Task '{task.id}' queued for Antigravity execution in workspace '{project.name}'.",
                        }, indent=2)
                    )
                ]
            )

        elif name == "continue_agent_session":
            session_id = arguments.get("session_id", "")
            prompt = arguments.get("prompt", "")
            priority = arguments.get("priority", TaskPriority.NORMAL)

            parent_task = (
                db.query(Task)
                .filter(Task.session_id == session_id)
                .order_by(Task.created_at.desc())
                .first()
            )
            if not parent_task:
                return McpToolResult(content=[McpContentItem(text=f"Error: Session '{session_id}' not found.")], isError=True)

            task = Task(
                project_id=parent_task.project_id,
                parent_task_id=parent_task.id,
                session_id=session_id,
                prompt=prompt,
                priority=priority,
                status=TaskStatus.QUEUED,
            )
            db.add(task)
            db.commit()
            db.refresh(task)

            await orchestrator.enqueue_task(task.id, priority=priority)

            return McpToolResult(
                content=[
                    McpContentItem(
                        text=json.dumps({
                            "task_id": task.id,
                            "parent_task_id": parent_task.id,
                            "session_id": session_id,
                            "status": "queued",
                            "message": f"Continuation queued in session '{session_id}'.",
                        }, indent=2)
                    )
                ]
            )

        elif name == "get_agent_session":
            session_id = arguments.get("session_id", "")
            tasks = (
                db.query(Task)
                .filter(Task.session_id == session_id)
                .order_by(Task.created_at.asc())
                .all()
            )
            if not tasks:
                return McpToolResult(content=[McpContentItem(text=f"Error: No records for session '{session_id}'.")], isError=True)

            history = [
                {
                    "task_id": t.id,
                    "prompt": t.prompt,
                    "status": t.status,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                }
                for t in tasks
            ]
            return McpToolResult(
                content=[
                    McpContentItem(
                        text=json.dumps({
                            "session_id": session_id,
                            "project_id": tasks[0].project_id,
                            "task_count": len(tasks),
                            "history": history,
                        }, indent=2)
                    )
                ]
            )

        elif name == "get_task_status":
            task_id = arguments.get("task_id", "")
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                return McpToolResult(content=[McpContentItem(text=f"Error: Task '{task_id}' not found.")], isError=True)

            resp_data = {
                "task_id": task.id,
                "project_id": task.project_id,
                "session_id": task.session_id,
                "status": task.status,
                "response": task.antigravity_response,
                "error": task.error_info,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            }
            return McpToolResult(content=[McpContentItem(text=json.dumps(resp_data, indent=2))])

        elif name == "get_task_events":
            task_id = arguments.get("task_id", "")
            limit = int(arguments.get("limit", 50))
            logs = (
                db.query(ExecutionLog)
                .filter(ExecutionLog.task_id == task_id)
                .order_by(ExecutionLog.timestamp.asc())
                .limit(limit)
                .all()
            )
            events = [
                {
                    "step_index": log.step_index,
                    "level": log.level,
                    "message": log.message,
                    "tool_name": log.tool_name,
                    "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                }
                for log in logs
            ]
            return McpToolResult(content=[McpContentItem(text=json.dumps(events, indent=2))])

        elif name == "cancel_agent_session":
            target = arguments.get("session_id", "")
            task = db.query(Task).filter(Task.id == target).first()
            if not task:
                task = (
                    db.query(Task)
                    .filter(Task.session_id == target, Task.status.in_([TaskStatus.QUEUED, TaskStatus.RUNNING]))
                    .first()
                )

            if not task:
                return McpToolResult(content=[McpContentItem(text=f"Error: No active task found for '{target}'.")], isError=True)

            success = await orchestrator.cancel_task(task.id)
            return McpToolResult(content=[McpContentItem(text=f"Cancellation requested for task '{task.id}'. Success: {success}")])

        elif name == "get_system_status":
            provider = provider_registry.get_provider()
            health = await provider.check_health()
            workspaces = workspace_service.list_authorized_workspaces()
            status_data = {
                "bridge_status": "operational",
                "active_provider": provider.provider_id,
                "agent_health": health,
                "authorized_workspaces_count": len(workspaces),
                "authorized_workspaces": [
                    {"id": w.id, "name": w.name, "path": w.path, "exists": w.exists_on_disk}
                    for w in workspaces
                ],
            }
            return McpToolResult(content=[McpContentItem(text=json.dumps(status_data, indent=2))])

        # Reverse tools
        elif name == "bridge_report_task_progress":
            from app.orchestration.logger import execution_logger
            task_id = arguments.get("task_id", "")
            level = arguments.get("level", "info")
            msg = arguments.get("message", "")
            tool_name = arguments.get("tool_name")
            await execution_logger.log_and_broadcast(task_id=task_id, message=msg, level=level, tool_name=tool_name)
            return McpToolResult(content=[McpContentItem(text="Progress recorded.")])

        elif name == "bridge_store_task_artifact":
            task_id = arguments.get("task_id", "")
            fn = arguments.get("filename", "")
            return McpToolResult(content=[McpContentItem(text=f"Artifact '{fn}' recorded for task '{task_id}'.")])

        else:
            return McpToolResult(content=[McpContentItem(text=f"Unknown tool: {name}")], isError=True)

    except BridgeException as e:
        return McpToolResult(content=[McpContentItem(text=f"Error: {e.detail}")], isError=True)
    except Exception as e:
        logger.exception("Error executing MCP tool '%s': %s", name, e)
        return McpToolResult(content=[McpContentItem(text=f"Internal Error: {str(e)}")], isError=True)
    finally:
        if should_close:
            db.close()
