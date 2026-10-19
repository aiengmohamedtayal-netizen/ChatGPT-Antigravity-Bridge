---
name: chatgpt-antigravity-bridge
description: >-
  Orchestrate multi-workspace local coding tasks, bounded filesystem operations,
  and stateful Google Antigravity agent sessions over MCP. Trigger whenever the
  user asks to list or switch local workspaces, read/write/search files across
  authorized repositories, dispatch implementation or refactoring tasks to
  Google Antigravity, continue an existing Antigravity session, or monitor
  automated build/test self-healing telemetry.
version: "1.0.0"
license: MIT
author: ChatGPT-Antigravity-Bridge Contributors
tags:
  - mcp
  - antigravity
  - multi-workspace
  - code-orchestration
  - claude-code
  - cursor
  - copilot
  - windsurf
  - codex
  - chatgpt
compatibility:
  mcp_protocol: "2024-11-05"
  transports:
    - stdio
    - sse
  agents:
    - claude-code
    - cursor
    - github-copilot
    - windsurf
    - openai-codex-cli
    - chatgpt-desktop
    - chatgpt-custom-gpt
---

# ChatGPT × Antigravity Bridge — Agent Skill Instructions

You are connected to the **ChatGPT × Antigravity Bridge** Model Context Protocol (MCP) server (`antigravity-bridge`). This bridge acts as a secure local control plane that connects high-level architectural planning (in Claude Code, Cursor, GitHub Copilot, Windsurf, OpenAI Codex CLI, or ChatGPT) with autonomous local code execution powered by **Google Antigravity** and a **Workspace Boundary Guard**.

---

## 1. WHEN to Trigger This Skill

Activate this skill and invoke the `antigravity-bridge` MCP tools whenever the user's request involves any of the following scenarios:

1. **Multi-Workspace Discovery & Cross-Repo Navigation**
   - The user asks what local projects or workspaces are available, or wants to inspect/modify files in a secondary repository registered in `workspaces.json` (e.g., `"Check my smart home repo"`, `"List all authorized workspaces"`, `"Search for auth middleware across my training workspace"`).
2. **Delegating Autonomous Coding & Refactoring to Google Antigravity**
   - The user wants to offload multi-file implementation, test generation, or build verification to the local Google Antigravity agent runtime (`send_agent_command`) while keeping the current conversation focused on high-level architecture and review.
3. **Stateful Multi-Turn Agent Continuation**
   - The user wants to follow up on a previously dispatched Antigravity task (`continue_agent_session`) so the agent continues inside the **exact same conversation context (`session_id`)** without re-scanning the entire repository.
4. **Security-Bounded Filesystem Operations (Remote or Local)**
   - You are operating from a remote/sandboxed client (e.g., ChatGPT Custom GPT, ChatGPT Desktop MCP, or a scoped IDE session) and need canonical-path-guarded read/write/search access to local disk directories (`read_file`, `write_file`, `search_files`, `get_file_tree`).

### When NOT to Trigger
- Do **not** invoke `send_agent_command` for trivial single-line questions that can be answered directly from files already in your context window.
- Do **not** attempt to access system roots (`C:\Windows`, `/etc`, `/usr`) or paths outside authorized workspaces—the `WorkspaceBoundaryGuard` will reject them.

---

## 2. HOW to Orchestrate Tasks (4-Step Execution Protocol)

Always follow this deterministic 4-step workflow when executing tasks through the Bridge:

### Step 1: Discover & Resolve Target Workspace
Never guess workspace IDs or filesystem paths. First query the registered workspaces:
- Call `list_workspaces` (or `list_projects`) to retrieve all authorized `workspace_id` / `project_id` entries, their canonical paths, and disk existence status.
- If the user created a new project folder on disk that is not yet listed, call `discover_workspaces` or `refresh_workspaces`.

### Step 2: Gather Bounded Context Before Dispatching
Before writing files or dispatching an Antigravity session, inspect the project layout using minimal tokens:
- Call `get_project_context` with `project_id` to read `AGENTS.md` guidelines, instructions, and tracked file counts.
- Call `get_file_tree` (default `max_depth=3`) or `search_files` (`search_type="filename"` or `"content"`) to locate exact target files.
- Call `read_file` with `workspace_id` and `path` to inspect specific modules.

### Step 3: Choose Direct Filesystem Edit vs. Antigravity Delegation

| Task Complexity | Recommended Action | MCP Tool(s) to Call |
| :--- | :--- | :--- |
| **Fast Inspection / Single-File Edit** | Perform directly via bounded filesystem tools | `read_file`, `write_file`, `create_directory`, `move_file` |
| **Multi-File Feature / Refactor + Auto-Verify** | Delegate to Google Antigravity queue worker | `send_agent_command` (with `project_id`, `prompt`, `priority`) |
| **Iterative Follow-Up on Previous Task** | Reuse the active session ID for zero context loss | `continue_agent_session` (with `session_id`, `prompt`) |
| **Abort Stuck or Unwanted Execution** | Cancel the active task cleanly | `cancel_agent_session` (with `session_id` or `task_id`) |

### Step 4: Monitor Telemetry & Self-Healing Verification
When you dispatch a task via `send_agent_command` or `continue_agent_session`:
1. Record the returned `task_id` and `session_id`.
2. Poll `get_task_status(task_id=...)` to track state transitions: `queued` → `running` → `verifying` → `completed` / `failed`.
3. Call `get_task_events(task_id=..., limit=50)` to stream structured execution steps and verification logs.
4. Note that during the `verifying` phase, the Bridge automatically runs project builds/tests (`pytest`, `npm test`, `npm run build`) and **self-heals up to 2 times** if verification fails. Wait for terminal status (`completed` or `failed`) before presenting the final summary.

---

## 3. Prompt Crafting Rules for `send_agent_command`

When delegating to Google Antigravity via `send_agent_command` or `continue_agent_session`, structure the `prompt` payload for maximum autonomous accuracy:

1. **Specify Target Files Explicitly**: Include relative paths discovered during Step 2 (e.g., `"Update app/services/auth.py and add unit tests in tests/test_auth.py"`).
2. **State Verification Criteria**: Tell Antigravity how to verify its changes (e.g., `"Ensure pytest tests/test_auth.py passes with zero warnings"`).
3. **Preserve Session Continuity**:
   - First task in a workflow: Call `send_agent_command(project_id="...", prompt="...")` (or initialize explicitly with `create_agent_session`).
   - Every subsequent task in the same feature flow: Pass the existing `session_id` to `continue_agent_session(session_id="...", prompt="...")`.

---

## 4. Security & Safety Guardrails

- **Workspace Scoping**: Always pass `workspace_id` (or `project_id`) when calling filesystem or project tools to enforce strict cross-workspace isolation.
- **Explicit Deletion Confirmation**: `delete_file` requires `confirm=True`. Never set `confirm=True` or `recursive=True` unless the user explicitly requested deletion of that specific path.
- **Zero Secret Leakage**: Never write raw API keys or `.env` credentials into source files or task prompts.

---

## 5. Progressive Disclosure References

Load these supplementary reference files only when needed:
- **Client Setup & MCP Config Templates**: See [`references/client-configs.md`](references/client-configs.md) for copy-pasteable `stdio` and `SSE` configurations for Claude Code, Cursor, GitHub Copilot, Windsurf, OpenAI Codex CLI, and ChatGPT.
- **Complete MCP Tool Schemas & Error Recovery**: See [`references/mcp-tools-reference.md`](references/mcp-tools-reference.md) for full parameter definitions and troubleshooting steps.
