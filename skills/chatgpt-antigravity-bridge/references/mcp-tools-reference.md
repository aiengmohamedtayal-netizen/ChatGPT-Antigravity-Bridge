# MCP Tools Schema & Error Recovery Reference

Complete technical specification of the 28 MCP tools exposed by `antigravity-bridge` (MCP Protocol `2024-11-05`).

---

## 1. Dynamic Workspace & Filesystem Tools (12 Tools)

All filesystem operations are validated by `WorkspaceBoundaryGuard` using canonical `os.path.realpath` resolution. Any attempt to traverse outside registered `workspaces.json` roots returns an explicit access error.

| Tool Name | Required Args | Optional Args | Purpose |
| :--- | :--- | :--- | :--- |
| `list_workspaces` | — | `enabled_only` (`bool`, default `true`) | List all authorized workspace roots, IDs, paths, and disk status. |
| `get_workspace` | `workspace_id` (`str`) | — | Inspect metadata, custom instructions, and root directory preview. |
| `discover_workspaces` | — | — | Auto-scan configured developer roots and register discovered projects. |
| `refresh_workspaces` | — | — | Reload `workspaces.json` from disk without restarting the server. |
| `list_directory` | — | `path` (`str`), `workspace_id` (`str`), `show_hidden` (`bool`) | List files and directories with size and modification timestamps. |
| `read_file` | `path` (`str`) | `workspace_id` (`str`), `max_bytes` (`int`, default `1000000`), `offset` (`int`, default `0`) | Read UTF-8 file contents with byte-offset pagination. |
| `write_file` | `path` (`str`), `content` (`str`) | `workspace_id` (`str`), `overwrite` (`bool`, default `true`) | Write or overwrite a file; automatically creates missing parent folders. |
| `create_directory` | `path` (`str`) | `workspace_id` (`str`) | Create directory hierarchy (`mkdir -p` behavior). |
| `move_file` | `source_path` (`str`), `target_path` (`str`) | `workspace_id` (`str`), `overwrite` (`bool`, default `false`) | Move or rename files/directories within authorized roots. |
| `delete_file` | `path` (`str`), `confirm` (`bool`) | `workspace_id` (`str`), `recursive` (`bool`, default `false`) | Delete a file or folder. **Must pass `confirm=true`**. |
| `search_files` | `query` (`str`) | `workspace_id` (`str`), `search_type` (`"filename"` \| `"content"`), `max_results` (`int`, default `50`) | Search across one or all workspaces by glob pattern or text substring. |
| `get_file_tree` | — | `workspace_id` (`str`), `path` (`str`), `max_depth` (`int`, 1–5), `max_entries` (`int`, default `200`) | Retrieve a bounded directory tree structure. |

---

## 2. Antigravity Control Plane & Orchestration Tools (13 Tools)

Use these tools to manage projects, dispatch autonomous coding prompts to Google Antigravity, continue existing sessions, and monitor verification results.

| Tool Name | Required Args | Optional Args | Purpose |
| :--- | :--- | :--- | :--- |
| `list_projects` | — | `enabled_only` (`bool`, default `true`) | List authorized projects along with active Antigravity session IDs. |
| `get_project` | `project_id` (`str`) | — | Retrieve project metadata, workspace path, and active session list. |
| `get_project_context` | `project_id` (`str`) | — | Read `AGENTS.md`, project instructions, file count, and sample files. |
| `get_project_tree` | `project_id` (`str`) | `subpath` (`str`), `max_depth` (`int`, 1–4) | Retrieve a project-scoped directory tree. |
| `list_agent_sessions` | `project_id` (`str`) | — | List historical and active Antigravity sessions for a project. |
| `create_agent_session` | — | `project_id` (`str`), `workspace_id` (`str`), `title` (`str`) | Pre-initialize a new stateful Antigravity session (`session_id`). |
| `send_agent_command` | `prompt` (`str`) | `project_id` (`str`), `workspace_id` (`str`), `session_id` (`str`), `priority` (`"low"`\|`"normal"`\|`"high"`\|`"urgent"`) | **Primary Dispatch Tool**: Enqueue a coding or refactoring task for Antigravity execution. |
| `continue_agent_session` | `session_id` (`str`), `prompt` (`str`) | `priority` (`"low"`\|`"normal"`\|`"high"`\|`"urgent"`) | Send a follow-up prompt in the **same** Antigravity session. |
| `get_agent_session` | `session_id` (`str`) | — | Retrieve full prompt and task status history for a session. |
| `get_task_status` | `task_id` (`str`) | — | Poll task status (`queued`, `running`, `verifying`, `completed`, `failed`) and agent response. |
| `get_task_events` | `task_id` (`str`) | `limit` (`int`, default `50`) | Fetch ordered execution telemetry and tool events for a task. |
| `cancel_agent_session` | `session_id` (`str`) | — | Cancel a queued or running task by `session_id` or `task_id`. |
| `get_system_status` | — | — | Check Bridge operational health, active provider, and workspace count. |

---

## 3. Reverse Callback Telemetry Tools (3 Tools)

Used internally by Google Antigravity when reporting progress back to the Bridge:

- `bridge_get_project_context(project_id)`: Fetches workspace context and guidelines.
- `bridge_report_task_progress(task_id, message, level, tool_name)`: Emits real-time execution logs.
- `bridge_store_task_artifact(task_id, filename, content, mime_type)`: Stores diffs, build logs, or test outputs.

---

## 4. Error Handling & Recovery Patterns

1. **`Error: Project/Workspace '<id>' not found`**
   - **Cause**: The provided `workspace_id` or `project_id` does not match an entry in `workspaces.json`.
   - **Recovery**: Call `list_workspaces` first to inspect valid IDs, or call `discover_workspaces` / `refresh_workspaces` if a workspace was recently added.
2. **`Access denied: this path is outside the authorized workspace roots`**
   - **Cause**: Path resolution escaped the authorized workspace root or referenced a restricted OS directory.
   - **Recovery**: Pass a relative path together with an explicit `workspace_id` (e.g., `workspace_id="proj_tool"`, `path="app/main.py"`).
3. **Task Status Transitions to `failed`**
   - **Cause**: The underlying build/test verification failed after 2 automatic self-healing retries, or the local Antigravity Language Server is unreachable.
   - **Recovery**: Call `get_task_events(task_id=...)` to inspect the failure log, then either fix the issue directly with `write_file` or send a targeted remediation prompt via `continue_agent_session`.
