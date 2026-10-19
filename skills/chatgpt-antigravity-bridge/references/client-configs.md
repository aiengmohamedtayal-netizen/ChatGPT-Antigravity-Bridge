# Client MCP Configuration & Setup Reference

This guide provides ready-to-use configuration snippets to connect **ChatGPT × Antigravity Bridge** across all major AI coding agents using either **Local Stdio** (zero network daemon required) or **Remote HTTP/SSE** (for cloud agents or shared local daemons).

---

## Prerequisites

1. Clone and install dependencies inside the bridge repository:
   ```bash
   git clone https://github.com/aiengmohamedtayal-netizen/ChatGPT-Antigravity-Bridge.git
   cd ChatGPT-Antigravity-Bridge
   python -m venv .venv
   # Windows: .venv\Scripts\activate | macOS/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env
   ```
2. Register your authorized project directories in `workspaces.json` at the repository root.

---

## 1. Claude Code (Anthropic CLI & IDE Extension)

### Skill Installation
Copy the `chatgpt-antigravity-bridge` skill folder into your Claude skills directory:
- **Project-scoped**: `.claude/skills/chatgpt-antigravity-bridge/SKILL.md`
- **Global user-scoped**: `~/.claude/skills/chatgpt-antigravity-bridge/SKILL.md`

### Option A: Local Stdio Transport (Recommended for Local Dev)
Run from your terminal or add to `.mcp.json`:
```bash
claude mcp add antigravity-bridge -- python -m app.mcp.server
```
Or in `.mcp.json`:
```json
{
  "mcpServers": {
    "antigravity-bridge": {
      "command": "python",
      "args": ["-m", "app.mcp.server"],
      "cwd": "/absolute/path/to/ChatGPT-Antigravity-Bridge"
    }
  }
}
```

### Option B: SSE Transport (Shared Running Gateway)
Start `python run.py` first, then configure:
```json
{
  "mcpServers": {
    "antigravity-bridge": {
      "type": "sse",
      "url": "http://127.0.0.1:8000/mcp/sse"
    }
  }
}
```

---

## 2. Cursor IDE

### Skill Installation
Place the skill folder in `.cursor/skills/chatgpt-antigravity-bridge/` (or reference `SKILL.md` in `.cursor/rules/`).

### MCP Configuration (`.cursor/mcp.json` or `~/.cursor/mcp.json`)

**Stdio Mode:**
```json
{
  "mcpServers": {
    "antigravity-bridge": {
      "command": "python",
      "args": ["-m", "app.mcp.server"],
      "cwd": "/absolute/path/to/ChatGPT-Antigravity-Bridge"
    }
  }
}
```

**SSE Mode (when running `python run.py`):**
```json
{
  "mcpServers": {
    "antigravity-bridge": {
      "url": "http://127.0.0.1:8000/mcp/sse"
    }
  }
}
```

---

## 3. GitHub Copilot & VS Code Agent Mode

### Skill Installation
Copy the skill folder to `.github/skills/chatgpt-antigravity-bridge/SKILL.md` or reference it in `.github/copilot-instructions.md`.

### MCP Configuration (`.vscode/mcp.json`)
```json
{
  "servers": {
    "antigravity-bridge": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "app.mcp.server"],
      "cwd": "/absolute/path/to/ChatGPT-Antigravity-Bridge"
    }
  }
}
```
*(Alternatively, use `"type": "sse"` and `"url": "http://127.0.0.1:8000/mcp/sse"` if running the gateway daemon).*

---

## 4. Windsurf (Codeium Cascade) & OpenAI Codex CLI

### Windsurf Configuration (`~/.codeium/windsurf/mcp_config.json`)
```json
{
  "mcpServers": {
    "antigravity-bridge": {
      "command": "python",
      "args": ["-m", "app.mcp.server"],
      "cwd": "/absolute/path/to/ChatGPT-Antigravity-Bridge"
    }
  }
}
```

### OpenAI Codex CLI (`~/.codex/config.toml` or MCP flags)
Install the skill into `~/.codex/skills/chatgpt-antigravity-bridge/SKILL.md` and register the MCP server:
```toml
[mcp_servers.antigravity-bridge]
command = "python"
args = ["-m", "app.mcp.server"]
cwd = "/absolute/path/to/ChatGPT-Antigravity-Bridge"
```

---

## 5. ChatGPT Desktop & Custom GPT Actions (Remote Cloud)

Because ChatGPT runs in the cloud, launch the Bridge with the included Cloudflare Quick Tunnel:
```bash
python scripts/gateway_manager.py
# Or manually:
# Terminal 1: python run.py
# Terminal 2: python run_tunnel.py
```

### ChatGPT Desktop App (Remote MCP over SSE)
```json
{
  "mcpServers": {
    "antigravity-bridge": {
      "url": "https://<YOUR_CLOUDFLARE_TUNNEL>.trycloudflare.com/mcp/sse"
    }
  }
}
```

### ChatGPT Custom GPT (OpenAPI 3.1 Action)
1. **Action Schema URL**: `https://<YOUR_CLOUDFLARE_TUNNEL>.trycloudflare.com/api/v1/chatgpt/openapi.json`
2. **Authentication**: Bearer Token using `<YOUR_BRIDGE_API_KEY>` (generated on first startup in `.initial_api_key.txt`).
3. **Instructions**: Paste the contents of `SKILL.md` into the Custom GPT Instructions panel.
