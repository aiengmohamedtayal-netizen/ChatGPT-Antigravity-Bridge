# ChatGPT Setup Guide

This guide walks through connecting ChatGPT to your local Antigravity Bridge instance.

---

## 1. Prerequisites

1. The Bridge server is running locally on port 8000:
   ```bash
   python run.py
   ```
2. The Cloudflare tunnel is active:
   ```bash
   python run_tunnel.py
   ```
   or double-click `START GATEWAY.bat`.

The launcher outputs your active public HTTPS URL and copies the MCP endpoint to your clipboard.

Example output:
```text
Public Tunnel URL:          https://<your-tunnel-id>.trycloudflare.com
ChatGPT OpenAPI Action:     https://<your-tunnel-id>.trycloudflare.com/api/v1/chatgpt/openapi.json
ChatGPT Remote MCP SSE:     https://<your-tunnel-id>.trycloudflare.com/mcp/sse
```

---

## 2. Option A: Custom GPT with Actions (Web, iOS, Android)

Use this method to let ChatGPT orchestrate Antigravity through standard OpenAPI actions from chatgpt.com or the ChatGPT mobile app.

### Step 1: Create a Custom GPT
1. Navigate to [chatgpt.com](https://chatgpt.com) -> **Explore GPTs** -> **Create**.
2. Switch to the **Configure** tab:
   - **Name**: `Antigravity Architect`
   - **Description**: `Architect and orchestrator for local Google Antigravity autonomous development sessions.`

### Step 2: Add Actions via OpenAPI Schema
1. Under **Actions**, click **Create new action**.
2. In the Schema section, click **Import from URL**.
3. Enter your action URL:
   ```text
   https://<your-tunnel-id>.trycloudflare.com/api/v1/chatgpt/openapi.json
   ```
   ChatGPT will import the available operations (`listProjects`, `getProject`, `getProjectContext`, `createAgentSession`, `sendAgentCommand`, `continueSession`, `getTaskStatus`, etc.).

### Step 3: Configure Authentication
1. In the **Authentication** section, click the settings gear:
   - **Authentication Type**: `API Key`
   - **Auth Type**: `Bearer`
   - **API Key**: Enter the key generated at startup (found in `.initial_api_key.txt` or created in the web dashboard).
2. Save the action configuration.

### Step 4: System Instructions
Paste this template into the **Instructions** box:

```markdown
You are the Lead Software Architect directing a local Google Antigravity agent through the Bridge Gateway.

### Workflow:
1. DISCOVERY: Call `listProjects` to check authorized local workspaces.
2. CONTEXT: Call `getProjectContext` to read guidelines, repository layout, and conventions before planning changes.
3. DISPATCH: Call `sendAgentCommand` with the target `project_id` and a detailed prompt describing what files to create or modify.
4. MONITORING: Call `getTaskStatus` to poll task progress until status is `completed` or `failed`.
5. ITERATION: If the user asks for follow-ups, refinements, or bug fixes, call `continueSession` referencing the previous task ID. This preserves the existing session state and workspace context.
```

---

## 3. Option B: ChatGPT Desktop (Remote MCP)

If you use the ChatGPT Desktop application with developer MCP support enabled, you can connect directly via SSE.

Add the following to your desktop MCP configuration file:

```json
{
  "mcpServers": {
    "antigravity-bridge": {
      "url": "https://<your-tunnel-id>.trycloudflare.com/mcp/sse"
    }
  }
}
```

When connected, ChatGPT receives the complete control plane toolset:
- `list_projects`: Inspect registered workspace directories.
- `get_project_context`: Read project guidelines and repository context.
- `get_project_tree`: Security-bounded directory tree within workspace boundaries.
- `send_agent_command`: Send coding prompts to Antigravity.
- `continue_agent_session`: Continue multi-turn sessions with full context.
- `get_task_status`: Retrieve task state, duration, and output logs.
- `cancel_agent_session`: Abort in-flight tasks cleanly.

---

## 4. Security Notes

- **Loopback binding**: The local FastAPI server binds to `127.0.0.1:8000`. No router port forwarding or public listening ports are opened.
- **Path boundary guard**: File operations and directory tree inspection are strictly sandboxed within authorized workspace paths. Traversal attempts (e.g. `../`) are rejected.
- **Token verification**: All endpoints require valid `Bearer` API keys, hashed with SHA-256 and compared in constant time.
