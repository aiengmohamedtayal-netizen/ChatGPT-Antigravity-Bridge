# Model Context Protocol (MCP) Guide

The **ChatGPT × Antigravity Bridge** provides a native MCP server compliant with the **2024-11-05 MCP Specification**.

---

## 1. Supported Transports

1. **Remote HTTP / Server-Sent Events (SSE)**:
   - Endpoint: `http://127.0.0.1:8000/mcp/sse`
   - Messages: `POST http://127.0.0.1:8000/mcp/messages?session_id=<id>`
2. **Standard I/O (Stdio)**:
   - Command: `python -m app.mcp.server`

---

## 2. Antigravity Configuration

To connect Google Antigravity to the Bridge's MCP server, open `~/.gemini/antigravity/mcp_config.json` and add:

```json
{
  "mcpServers": {
    "antigravity-bridge": {
      "url": "http://127.0.0.1:8000/mcp/sse"
    }
  }
}
```

Or for Stdio:

```json
{
  "mcpServers": {
    "antigravity-bridge": {
      "command": "python",
      "args": ["-m", "app.mcp.server"],
      "cwd": "/path/to/ChatGPT-Antigravity-Bridge"
    }
  }
}
```

---

## 3. Exported Tools Reference

### `bridge_get_project_context`
Returns deep workspace context including directory trees, guidelines, and active task state.
- **Parameters**: `project_id` (string)

### `bridge_report_task_progress`
Allows Antigravity to emit real-time logs, thoughts, and tool call progress directly back to the Bridge dashboard and ChatGPT.
- **Parameters**: `task_id` (string), `message` (string), `level` (string), `tool_name` (string, optional)

### `bridge_store_task_artifact`
Persists files, code diffs, or build logs generated during execution.
- **Parameters**: `task_id` (string), `filename` (string), `content` (string), `mime_type` (string, optional)

### `bridge_query_task_history`
Returns preceding architectural decisions and task summaries for a project.
- **Parameters**: `project_id` (string), `limit` (integer, default 5)
