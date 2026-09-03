/**
 * ChatGPT × Antigravity Bridge - Premium 3D Landing Page Engine
 */

(function () {
  'use strict';

  // --- State & Config ---
  const state = {
    theme: localStorage.getItem('agb_theme') || 'dark',
    activeSimStep: 1,
    activePreset: 'oauth',
    activeIntegTab: 'chatgpt',
    activeTool: 'send_agent_command',
    wireframeMode: false,
    particlesCount: 40,
    serverStatus: 'checking',
    latencyMs: 0,
  };

  // Preset Workflows for Live Simulator
  const SIM_PRESETS = {
    oauth: {
      title: "OAuth2 & JWT Auth Implementation",
      prompt: "Implement OAuth2 Bearer token authentication with bcrypt password hashing and token revocation in app/security/auth.py.",
      endpoint: "/api/v1/tasks",
      method: "POST",
      reqBody: {
        project_id: "proj_default",
        prompt: "Implement OAuth2 Bearer token authentication with bcrypt password hashing and token revocation in app/security/auth.py.",
        priority: "high"
      },
      terminalLogs: [
        { time: "0.00s", type: "info", text: "[GATEWAY] Task dispatched to Priority Queue (Priority: HIGH, Target: proj_default)" },
        { time: "0.04s", type: "info", text: "[GATEWAY] Bearer Token Authenticated (Scope: tasks:create, Actor: chatgpt-custom-action)" },
        { time: "0.08s", type: "dim", text: "[SECURITY] Path boundary validated: 'd:/PROJECTS/tool/app/security/auth.py' is within workspace." },
        { time: "0.15s", type: "info", text: "[ANTIGRAVITY] Session created. Initializing AST parser and dependency tree..." },
        { time: "0.42s", type: "dim", text: "[AST] Inspecting existing app/core/security.py & models/api_key.py..." },
        { time: "0.85s", type: "success", text: "[EDIT] Generated app/security/auth.py (JWT decode, expiration check, bcrypt verification)" },
        { time: "1.10s", type: "warn", text: "[EXEC] Running test suite: python -m pytest tests/test_auth.py -v" },
        { time: "1.65s", type: "success", text: "[EXEC] test_auth.py::test_jwt_roundtrip PASSED (17/17 tests passing)" },
        { time: "1.80s", type: "info", text: "[MCP] bridge_store_task_artifact -> 'app/security/auth.py' (3.8 KB)" },
        { time: "1.92s", type: "success", text: "[GATEWAY] Task completed in 1.92s. Ready for conversational continuation." }
      ],
      diffLines: [
        { type: "add", text: "+ async def verify_access_token(token: str = Depends(oauth2_scheme)) -> TokenPayload:" },
        { type: "add", text: "+     payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])" },
        { type: "add", text: "+     if is_token_revoked(payload.jti):" },
        { type: "add", text: "+         raise HTTPException(status_code=401, detail='Token has been revoked')" },
        { type: "add", text: "+     return payload" },
        { type: "del", text: "- # Legacy insecure authentication stub removed" }
      ]
    },
    sqlite: {
      title: "SQLite WAL Mode & Connection Pool Refactor",
      prompt: "Optimize database connection pooling in app/database.py to enable Write-Ahead Logging (WAL) and eliminate concurrency locks.",
      endpoint: "/api/v1/tasks",
      method: "POST",
      reqBody: {
        project_id: "proj_default",
        prompt: "Optimize database connection pooling in app/database.py to enable Write-Ahead Logging (WAL) and eliminate concurrency locks.",
        priority: "urgent"
      },
      terminalLogs: [
        { time: "0.00s", type: "info", text: "[GATEWAY] Task dispatched to Priority Queue (Priority: URGENT)" },
        { time: "0.03s", type: "dim", text: "[SECURITY] Validating SQLite lock safety..." },
        { time: "0.22s", type: "info", text: "[ANTIGRAVITY] Inspecting SQLAlchemy engine configuration in app/database.py" },
        { time: "0.58s", type: "success", text: "[EDIT] Applied PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;" },
        { time: "0.92s", type: "success", text: "[EDIT] Configured StaticPool with timeout=30.0s for multi-threaded concurrency" },
        { time: "1.25s", type: "warn", text: "[EXEC] Simulating 50 concurrent task submissions..." },
        { time: "1.50s", type: "success", text: "[BENCHMARK] 0 database locks encountered. Average write latency: 0.8ms" },
        { time: "1.72s", type: "success", text: "[GATEWAY] Task completed successfully." }
      ],
      diffLines: [
        { type: "add", text: "+ @event.listens_for(engine, 'connect')" },
        { type: "add", text: "+ def set_sqlite_pragma(dbapi_connection, connection_record):" },
        { type: "add", text: "+     cursor = dbapi_connection.cursor()" },
        { type: "add", text: "+     cursor.execute('PRAGMA journal_mode=WAL;')" },
        { type: "add", text: "+     cursor.execute('PRAGMA synchronous=NORMAL;')" },
        { type: "del", text: "- engine = create_engine(DATABASE_URL)" }
      ]
    },
    sse: {
      title: "Real-Time SSE Telemetry Endpoint",
      prompt: "Expose real-time task execution progress over Server-Sent Events (SSE) at /api/v1/tasks/{id}/events.",
      endpoint: "/api/v1/tasks",
      method: "POST",
      reqBody: {
        project_id: "proj_default",
        prompt: "Expose real-time task execution progress over Server-Sent Events (SSE) at /api/v1/tasks/{id}/events.",
        priority: "normal"
      },
      terminalLogs: [
        { time: "0.00s", type: "info", text: "[GATEWAY] Task dispatched (Priority: NORMAL)" },
        { time: "0.18s", type: "info", text: "[ANTIGRAVITY] Parsing EventSource spec and FastAPI StreamingResponse..." },
        { time: "0.75s", type: "success", text: "[EDIT] Added /tasks/{id}/events async generator listening to ExecutionLogger pub/sub" },
        { time: "1.10s", type: "warn", text: "[TEST] Verifying SSE ping intervals and client disconnect handling" },
        { time: "1.45s", type: "success", text: "[EXEC] SSE handshake verified with text/event-stream" },
        { time: "1.60s", type: "success", text: "[GATEWAY] Task completed." }
      ],
      diffLines: [
        { type: "add", text: "+ @router.get('/tasks/{task_id}/events')" },
        { type: "add", text: "+ async def stream_task_events(task_id: str):" },
        { type: "add", text: "+     async def event_generator():" },
        { type: "add", text: "+         async for msg in execution_logger.subscribe(task_id):" },
        { type: "add", text: "+             yield f'data: {json.dumps(msg)}\\n\\n'" },
        { type: "add", text: "+     return StreamingResponse(event_generator(), media_type='text/event-stream')" }
      ]
    },
    continuation: {
      title: "Multi-Turn Conversational Continuation",
      prompt: "Now add automated unit tests and benchmark the execution under 100 concurrent requests.",
      endpoint: "/api/v1/tasks/task_abc123/continue",
      method: "POST",
      reqBody: {
        prompt: "Now add automated unit tests and benchmark the execution under 100 concurrent requests."
      },
      terminalLogs: [
        { time: "0.00s", type: "info", text: "[GATEWAY] Continuation requested for parent_task_id: task_abc123" },
        { time: "0.02s", type: "success", text: "[CONTINUATION] Reusing Antigravity session 'sess_9942a1bc' (Multi-Turn Thread Active)" },
        { time: "0.05s", type: "dim", text: "[CONTEXT] Hydrated preceding diffs and assistant thought history..." },
        { time: "0.45s", type: "info", text: "[ANTIGRAVITY] Continuing from previous auth implementation. Writing tests/test_concurrency.py..." },
        { time: "0.90s", type: "success", text: "[EDIT] Created tests/test_concurrency.py with pytest-asyncio and httpx benchmark" },
        { time: "1.30s", type: "warn", text: "[EXEC] pytest tests/test_concurrency.py -v" },
        { time: "1.75s", type: "success", text: "[EXEC] 100 requests completed in 0.42s (0 errors, 100% pass)" },
        { time: "1.90s", type: "success", text: "[GATEWAY] Continuation task completed without losing any prior session state." }
      ],
      diffLines: [
        { type: "add", text: "+ @pytest.mark.asyncio" },
        { type: "add", text: "+ async def test_concurrent_sessions(client, auth_headers):" },
        { type: "add", text: "+     tasks = [client.get('/api/v1/projects', headers=auth_headers) for _ in range(100)]" },
        { type: "add", text: "+     results = await asyncio.gather(*tasks)" },
        { type: "add", text: "+     assert all(r.status_code == 200 for r in results)" }
      ]
    }
  };

  // Tools Database (12 Control Plane + 4 Internal MCP)
  const TOOLS_DATA = {
    send_agent_command: {
      name: "send_agent_command",
      protocol: "OpenAPI 3.1 & MCP",
      method: "POST",
      endpoint: "/api/v1/tasks",
      category: "Task Orchestration",
      description: "Primary tool used by ChatGPT to dispatch an autonomous development command to the local Antigravity Agent. Places task in the priority queue.",
      schema: [
        { param: "project_id", type: "string", required: true, desc: "Target project workspace identifier from allowlist" },
        { param: "prompt", type: "string", required: true, desc: "Specific software engineering instruction for Antigravity" },
        { param: "priority", type: "string", required: false, desc: "Execution priority: 'low', 'normal', 'high', or 'urgent' (default: normal)" }
      ],
      exampleReq: {
        project_id: "proj_default",
        prompt: "Refactor database migrations to use Alembic in app/migrations",
        priority: "high"
      },
      exampleRes: {
        id: "task_e481b9",
        status: "queued",
        project_id: "proj_default",
        session_id: "sess_7f21ca",
        priority: "high",
        created_at: "2026-09-03T21:28:00Z"
      }
    },
    continue_agent_session: {
      name: "continue_agent_session",
      protocol: "OpenAPI 3.1 & MCP",
      method: "POST",
      endpoint: "/api/v1/tasks/{task_id}/continue",
      category: "Multi-Turn Memory",
      description: "Dispatches a follow-up instruction to the exact SAME Antigravity session. Preserves all files, variables, and previous execution diffs.",
      schema: [
        { param: "task_id", type: "string", required: true, desc: "The ID of the prior completed task" },
        { param: "prompt", type: "string", required: true, desc: "Follow-up instruction or code refinement prompt" }
      ],
      exampleReq: {
        prompt: "Now add input validation schemas to the user signup endpoint."
      },
      exampleRes: {
        id: "task_c920f1",
        parent_task_id: "task_e481b9",
        session_id: "sess_7f21ca",
        status: "queued",
        is_continuation: true
      }
    },
    list_projects: {
      name: "list_projects",
      protocol: "OpenAPI 3.1 & MCP",
      method: "GET",
      endpoint: "/api/v1/projects",
      category: "Discovery",
      description: "Allows ChatGPT to discover all explicitly authorized project workspaces on the local machine without path traversal risk.",
      schema: [
        { param: "enabled_only", type: "boolean", required: false, desc: "Filter active projects only (default: true)" }
      ],
      exampleReq: {},
      exampleRes: [
        {
          id: "proj_default",
          name: "Tool Workspace",
          workspace_path: "d:/PROJECTS/tool",
          description: "Primary workspace directory for ChatGPT × Antigravity Bridge development.",
          status: "active"
        }
      ]
    },
    get_project_context: {
      name: "get_project_context",
      protocol: "OpenAPI 3.1 & MCP",
      method: "GET",
      endpoint: "/api/v1/projects/{project_id}/context",
      category: "Discovery",
      description: "Returns deep architectural context including AGENTS.md, tech stack, tracked files, and active development guidelines.",
      schema: [
        { param: "project_id", type: "string", required: true, desc: "Target project ID" }
      ],
      exampleReq: {},
      exampleRes: {
        project_id: "proj_default",
        name: "Tool Workspace",
        guidelines: "Follow clean architecture, write modular and tested code, never delete working code.",
        tracked_files: ["app/main.py", "app/database.py", "requirements.txt"]
      }
    },
    get_project_tree: {
      name: "get_project_tree",
      protocol: "OpenAPI 3.1 & MCP",
      method: "GET",
      endpoint: "/api/v1/projects/{project_id}/tree",
      category: "Discovery",
      description: "Returns a bounded file tree strictly confined to the workspace root. Prevents any relative directory traversal (e.g. ../../).",
      schema: [
        { param: "project_id", type: "string", required: true, desc: "Target project ID" },
        { param: "subpath", type: "string", required: false, desc: "Optional subfolder relative to workspace" },
        { param: "max_depth", type: "integer", required: false, desc: "Max recursion depth (1-4, default: 2)" }
      ],
      exampleReq: { project_id: "proj_default", max_depth: 2 },
      exampleRes: {
        root: "d:/PROJECTS/tool",
        tree: [
          { name: "app", type: "dir", children: ["api", "core", "models", "main.py"] },
          { name: "docs", type: "dir", children: ["ARCHITECTURE.md", "SECURITY.md"] },
          { name: "requirements.txt", type: "file", size: 244 }
        ]
      }
    },
    get_task_status: {
      name: "get_task_status",
      protocol: "OpenAPI 3.1 & MCP",
      method: "GET",
      endpoint: "/api/v1/tasks/{task_id}",
      category: "Observability",
      description: "Polls current execution status, execution logs, generated code, and files modified by the Antigravity agent.",
      schema: [
        { param: "task_id", type: "string", required: true, desc: "Unique task execution ID" }
      ],
      exampleReq: {},
      exampleRes: {
        id: "task_e481b9",
        status: "completed",
        antigravity_response: "Implemented Alembic migrations in app/migrations.",
        files_modified: ["app/migrations/env.py", "alembic.ini"],
        execution_time_seconds: 2.14
      }
    },
    get_task_events: {
      name: "get_task_events",
      protocol: "SSE & MCP",
      method: "GET",
      endpoint: "/api/v1/tasks/{task_id}/events",
      category: "Observability",
      description: "Server-Sent Events (SSE) telemetry stream emitting real-time agent thoughts, tool calls, shell executions, and completions.",
      schema: [
        { param: "task_id", type: "string", required: true, desc: "Target task ID" }
      ],
      exampleReq: {},
      exampleRes: "data: {\"event\": \"agent_started\", \"timestamp\": \"2026-09-03T21:28:02Z\"}\n\ndata: {\"event\": \"file_written\", \"path\": \"app/migrations/env.py\"}\n\n"
    },
    cancel_agent_session: {
      name: "cancel_agent_session",
      protocol: "OpenAPI 3.1 & MCP",
      method: "POST",
      endpoint: "/api/v1/tasks/{task_id}/cancel",
      category: "Task Orchestration",
      description: "Safely aborts a running Antigravity task and terminates active terminal child processes.",
      schema: [
        { param: "task_id", type: "string", required: true, desc: "ID of task to abort" }
      ],
      exampleReq: {},
      exampleRes: {
        status: "cancelled",
        task_id: "task_e481b9",
        message: "Agent process aborted gracefully."
      }
    },
    bridge_report_task_progress: {
      name: "bridge_report_task_progress",
      protocol: "Antigravity MCP Tool",
      method: "JSON-RPC",
      endpoint: "/mcp/sse",
      category: "Agent MCP",
      description: "Exported MCP tool invoked by Google Antigravity to report real-time thought progress and tool output back to ChatGPT.",
      schema: [
        { param: "task_id", type: "string", required: true, desc: "Current task ID" },
        { param: "message", type: "string", required: true, desc: "Status message or thought trace" },
        { param: "level", type: "string", required: false, desc: "'info', 'warn', or 'error'" }
      ],
      exampleReq: {
        task_id: "task_e481b9",
        message: "Refactoring model relations to support cascading delete",
        level: "info"
      },
      exampleRes: { success: true }
    },
    bridge_store_task_artifact: {
      name: "bridge_store_task_artifact",
      protocol: "Antigravity MCP Tool",
      method: "JSON-RPC",
      endpoint: "/mcp/sse",
      category: "Agent MCP",
      description: "Persists generated code diffs, logs, or build artifacts from Antigravity into the Bridge SQLite database.",
      schema: [
        { param: "task_id", type: "string", required: true, desc: "Task ID" },
        { param: "filename", type: "string", required: true, desc: "Artifact filename" },
        { param: "content", type: "string", required: true, desc: "File content or diff text" }
      ],
      exampleReq: {
        task_id: "task_e481b9",
        filename: "migration.sql",
        content: "CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT);"
      },
      exampleRes: { artifact_id: "art_1109a", bytes_stored: 54 }
    }
  };

  // --- Initializer ---
  document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    init3DVisualizer();
    initSimulator();
    initToolExplorer();
    initIntegrationTabs();
    initFaqAccordion();
    initLiveHealthCheck();
    initCopyButtons();
    initDynamicUrls();
  });

  // --- Theme Management ---
  function initTheme() {
    document.documentElement.setAttribute('data-theme', state.theme);
    const toggleBtn = document.getElementById('theme-toggle');
    if (toggleBtn) {
      toggleBtn.addEventListener('click', () => {
        state.theme = state.theme === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', state.theme);
        localStorage.setItem('agb_theme', state.theme);
        toggleBtn.innerHTML = state.theme === 'dark' ? '☀️' : '🌙';
      });
      toggleBtn.innerHTML = state.theme === 'dark' ? '☀️' : '🌙';
    }
  }

  // --- Live Health Check & Ping ---
  async function initLiveHealthCheck() {
    const statusPill = document.getElementById('status-pill');
    const pingEl = document.getElementById('hero-ping-ms');
    const providerEl = document.getElementById('hero-provider-name');

    async function checkHealth() {
      const t0 = performance.now();
      try {
        const res = await fetch('/health', { cache: 'no-store' });
        const latency = Math.round(performance.now() - t0);
        state.latencyMs = latency;

        if (res.ok) {
          const data = await res.json();
          state.serverStatus = 'online';
          if (statusPill) {
            statusPill.innerHTML = `<span class="status-dot"></span><span>Gateway Online (${latency}ms)</span>`;
            statusPill.style.borderColor = 'rgba(16, 163, 127, 0.4)';
          }
          if (pingEl) pingEl.innerText = `${latency}ms`;
          if (providerEl) providerEl.innerText = data.app ? "Antigravity Native SDK" : "Online";
        } else {
          throw new Error("HTTP " + res.status);
        }
      } catch (e) {
        state.serverStatus = 'offline';
        if (statusPill) {
          statusPill.innerHTML = `<span class="status-dot" style="background:#ef4444;box-shadow:0 0 10px #ef4444;"></span><span>Gateway Standby</span>`;
        }
        if (pingEl) pingEl.innerText = "Localhost";
      }
    }

    await checkHealth();
    setInterval(checkHealth, 8000);

    const pingBtn = document.getElementById('btn-ping-live');
    if (pingBtn) {
      pingBtn.addEventListener('click', async () => {
        showToast("⚡ Pinging local Bridge Gateway...");
        await checkHealth();
      });
    }
  }

  // --- Dynamic URLs (detects localhost or tunnel) ---
  function initDynamicUrls() {
    const origin = window.location.origin;
    const openapiEl = document.getElementById('code-openapi-url');
    if (openapiEl) openapiEl.innerText = `${origin}/api/v1/chatgpt/openapi.json`;

    const mcpSseEl = document.getElementById('code-mcp-sse-url');
    if (mcpSseEl) {
      mcpSseEl.innerText = `{\n  "mcpServers": {\n    "antigravity-gateway": {\n      "url": "${origin}/mcp/sse"\n    }\n  }\n}`;
    }
  }

  // ===================================================================
  // 3D NEURAL BRIDGE VISUALIZER ENGINE
  // ===================================================================
  function init3DVisualizer() {
    const canvas = document.getElementById('canvas-3d');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    let width = canvas.clientWidth;
    let height = canvas.clientHeight;

    function resize() {
      width = canvas.clientWidth;
      height = canvas.clientHeight;
      canvas.width = width * window.devicePixelRatio;
      canvas.height = height * window.devicePixelRatio;
      ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    }
    resize();
    window.addEventListener('resize', resize);

    // Mouse Parallax
    let mouse = { x: 0, y: 0, targetX: 0, targetY: 0 };
    window.addEventListener('mousemove', (e) => {
      const rect = canvas.getBoundingClientRect();
      const nx = (e.clientX - rect.left) / rect.width - 0.5;
      const ny = (e.clientY - rect.top) / rect.height - 0.5;
      mouse.targetX = nx * 35;
      mouse.targetY = ny * 35;
    });

    // 3D Particles on Neural Bridge
    const particles = [];
    for (let i = 0; i < state.particlesCount; i++) {
      particles.push({
        progress: Math.random(),
        speed: 0.003 + Math.random() * 0.005,
        offsetY: (Math.random() - 0.5) * 40,
        offsetZ: (Math.random() - 0.5) * 40,
        size: 2 + Math.random() * 3,
        color: Math.random() > 0.5 ? '#38bdf8' : '#10b981',
      });
    }

    // Energy Burst Packets
    const bursts = [];
    function launchPulseBurst() {
      for (let i = 0; i < 15; i++) {
        bursts.push({
          progress: 0,
          speed: 0.012 + Math.random() * 0.008,
          offsetY: (Math.random() - 0.5) * 30,
          offsetZ: (Math.random() - 0.5) * 30,
          size: 3.5 + Math.random() * 3,
          color: '#fbbf24',
        });
      }
      showToast("🚀 Prompt dispatched across 3D Neural Bridge!");
    }

    const pulseBtn = document.getElementById('btn-pulse-packet');
    if (pulseBtn) pulseBtn.addEventListener('click', launchPulseBurst);

    const wireframeBtn = document.getElementById('btn-toggle-wireframe');
    if (wireframeBtn) {
      wireframeBtn.addEventListener('click', () => {
        state.wireframeMode = !state.wireframeMode;
        wireframeBtn.classList.toggle('active', state.wireframeMode);
      });
    }

    let angle = 0;

    // Render Loop
    function render() {
      // Smooth mouse interpolation
      mouse.x += (mouse.targetX - mouse.x) * 0.08;
      mouse.y += (mouse.targetY - mouse.y) * 0.08;

      ctx.clearRect(0, 0, width, height);

      // Node Coordinates with 3D Parallax
      const chatgptNode = {
        x: width * 0.22 + mouse.x * 0.8,
        y: height * 0.5 + mouse.y * 0.8,
        radius: 46,
      };

      const antigravityNode = {
        x: width * 0.78 - mouse.x * 0.8,
        y: height * 0.5 - mouse.y * 0.8,
        radius: 46,
      };

      angle += 0.02;

      // 1. Draw Bridge Spline Tube & Energy Conduits
      ctx.save();
      const gradient = ctx.createLinearGradient(chatgptNode.x, chatgptNode.y, antigravityNode.x, antigravityNode.y);
      gradient.addColorStop(0, 'rgba(16, 163, 127, 0.6)');
      gradient.addColorStop(0.5, 'rgba(56, 189, 248, 0.8)');
      gradient.addColorStop(1, 'rgba(139, 92, 246, 0.6)');

      // Draw Multi-strand Energy Conduits
      const numStrands = state.wireframeMode ? 6 : 4;
      for (let s = 0; s < numStrands; s++) {
        const waveOffset = Math.sin(angle * 1.5 + s) * 14;
        ctx.beginPath();
        ctx.moveTo(chatgptNode.x, chatgptNode.y);
        ctx.bezierCurveTo(
          width * 0.4, height * 0.5 + waveOffset + mouse.y * 0.4,
          width * 0.6, height * 0.5 - waveOffset - mouse.y * 0.4,
          antigravityNode.x, antigravityNode.y
        );
        ctx.strokeStyle = gradient;
        ctx.lineWidth = s === 0 ? 3 : 1;
        ctx.shadowColor = '#38bdf8';
        ctx.shadowBlur = s === 0 ? 15 : 5;
        ctx.stroke();
      }
      ctx.restore();

      // 2. Draw 3D Continuous Particles
      particles.forEach((p) => {
        p.progress += p.speed;
        if (p.progress > 1) p.progress = 0;

        // Cubic bezier interpolation
        const t = p.progress;
        const cx1 = width * 0.4;
        const cy1 = height * 0.5 + p.offsetY;
        const cx2 = width * 0.6;
        const cy2 = height * 0.5 - p.offsetY;

        const bx = Math.pow(1 - t, 3) * chatgptNode.x +
                   3 * Math.pow(1 - t, 2) * t * cx1 +
                   3 * (1 - t) * Math.pow(t, 2) * cx2 +
                   Math.pow(t, 3) * antigravityNode.x;

        const by = Math.pow(1 - t, 3) * chatgptNode.y +
                   3 * Math.pow(1 - t, 2) * t * cy1 +
                   3 * (1 - t) * Math.pow(t, 2) * cy2 +
                   Math.pow(t, 3) * antigravityNode.y;

        ctx.save();
        ctx.beginPath();
        ctx.arc(bx, by, p.size, 0, Math.PI * 2);
        ctx.fillStyle = p.color;
        ctx.shadowColor = p.color;
        ctx.shadowBlur = 12;
        ctx.fill();
        ctx.restore();
      });

      // 3. Draw Burst Pulses
      for (let i = bursts.length - 1; i >= 0; i--) {
        const b = bursts[i];
        b.progress += b.speed;

        if (b.progress >= 1) {
          bursts.splice(i, 1);
          continue;
        }

        const t = b.progress;
        const bx = (1 - t) * chatgptNode.x + t * antigravityNode.x;
        const by = (1 - t) * chatgptNode.y + t * antigravityNode.y + Math.sin(t * Math.PI) * b.offsetY;

        ctx.save();
        ctx.beginPath();
        ctx.arc(bx, by, b.size, 0, Math.PI * 2);
        ctx.fillStyle = b.color;
        ctx.shadowColor = b.color;
        ctx.shadowBlur = 20;
        ctx.fill();
        ctx.restore();
      }

      // 4. Draw Left Node: ChatGPT Core (Geodesic Sphere & Orbital Rings)
      draw3DNode(ctx, chatgptNode.x, chatgptNode.y, chatgptNode.radius, '#10a37f', '#34d399', angle, 'ChatGPT', 'Lead Architect');

      // 5. Draw Right Node: Antigravity Agent (Crystalline Octahedron & Rings)
      draw3DNode(ctx, antigravityNode.x, antigravityNode.y, antigravityNode.radius, '#6366f1', '#38bdf8', -angle, 'Antigravity', 'Real Agent');

      requestAnimationFrame(render);
    }

    render();
  }

  function draw3DNode(ctx, x, y, radius, primaryColor, glowColor, rotation, title, subtitle) {
    ctx.save();

    // Orbital Rings
    for (let r = 1; r <= 2; r++) {
      ctx.beginPath();
      ctx.ellipse(x, y, radius * (1.3 + r * 0.35), radius * 0.5, rotation * r, 0, Math.PI * 2);
      ctx.strokeStyle = primaryColor;
      ctx.lineWidth = 1.2;
      ctx.globalAlpha = 0.45;
      ctx.stroke();
    }

    // Core Orb Glow
    const radGlow = ctx.createRadialGradient(x, y, 5, x, y, radius * 1.5);
    radGlow.addColorStop(0, primaryColor);
    radGlow.addColorStop(0.6, glowColor);
    radGlow.addColorStop(1, 'transparent');
    ctx.globalAlpha = 0.25;
    ctx.fillStyle = radGlow;
    ctx.beginPath();
    ctx.arc(x, y, radius * 1.5, 0, Math.PI * 2);
    ctx.fill();

    // Core Solid/Wireframe Sphere
    ctx.globalAlpha = 0.9;
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.fillStyle = '#060911';
    ctx.shadowColor = glowColor;
    ctx.shadowBlur = 25;
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = primaryColor;
    ctx.stroke();

    // Internal Wireframe Cross-lines
    ctx.beginPath();
    ctx.ellipse(x, y, radius * 0.8, radius * 0.3, rotation, 0, Math.PI * 2);
    ctx.strokeStyle = glowColor;
    ctx.lineWidth = 1;
    ctx.globalAlpha = 0.6;
    ctx.stroke();

    // Text Label inside 3D Orb
    ctx.globalAlpha = 1.0;
    ctx.font = 'bold 12px Inter, sans-serif';
    ctx.fillStyle = '#ffffff';
    ctx.textAlign = 'center';
    ctx.fillText(title, x, y + 4);

    ctx.restore();
  }

  // ===================================================================
  // INTERACTIVE WORKFLOW SIMULATOR
  // ===================================================================
  function initSimulator() {
    const stepBtns = document.querySelectorAll('.sim-step-btn');
    const presetChips = document.querySelectorAll('.preset-chip');
    const reqMethodEl = document.getElementById('sim-req-method');
    const reqPathEl = document.getElementById('sim-req-path');
    const reqJsonEl = document.getElementById('sim-req-json');
    const logsContainer = document.getElementById('sim-terminal-logs');
    const diffContainer = document.getElementById('sim-diff-lines');

    function updateSimulator() {
      const data = SIM_PRESETS[state.activePreset];
      if (!data) return;

      if (reqMethodEl) reqMethodEl.innerText = data.method;
      if (reqPathEl) reqPathEl.innerText = data.endpoint;
      if (reqJsonEl) {
        reqJsonEl.innerText = JSON.stringify(data.reqBody, null, 2);
      }

      // Stream terminal logs
      if (logsContainer) {
        logsContainer.innerHTML = '';
        data.terminalLogs.forEach((log, idx) => {
          setTimeout(() => {
            const line = document.createElement('div');
            line.className = `code-line terminal-line-${log.type}`;
            line.innerHTML = `<span class="code-comment">[${log.time}]</span> ${escapeHtml(log.text)}`;
            logsContainer.appendChild(line);
            logsContainer.scrollTop = logsContainer.scrollHeight;
          }, idx * 45);
        });
      }

      // Render Diff
      if (diffContainer) {
        diffContainer.innerHTML = '';
        data.diffLines.forEach((diff) => {
          const d = document.createElement('span');
          d.className = diff.type === 'add' ? 'diff-add' : 'diff-del';
          d.innerText = diff.text;
          diffContainer.appendChild(d);
        });
      }
    }

    // Step button clicks
    stepBtns.forEach((btn) => {
      btn.addEventListener('click', () => {
        const step = parseInt(btn.getAttribute('data-step'), 10);
        state.activeSimStep = step;
        stepBtns.forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');

        // Map step to appropriate preset
        if (step === 1) state.activePreset = 'oauth';
        else if (step === 2) state.activePreset = 'sqlite';
        else if (step === 3) state.activePreset = 'sse';
        else if (step === 4 || step === 5) state.activePreset = 'continuation';

        presetChips.forEach((c) => {
          c.classList.toggle('active', c.getAttribute('data-preset') === state.activePreset);
        });

        updateSimulator();
      });
    });

    // Preset chip clicks
    presetChips.forEach((chip) => {
      chip.addEventListener('click', () => {
        const p = chip.getAttribute('data-preset');
        state.activePreset = p;
        presetChips.forEach((c) => c.classList.remove('active'));
        chip.classList.add('active');
        updateSimulator();
      });
    });

    updateSimulator();
  }

  // ===================================================================
  // INTERACTIVE TOOL EXPLORER
  // ===================================================================
  function initToolExplorer() {
    const rowsContainer = document.getElementById('tool-rows-container');
    const searchInput = document.getElementById('tool-search');
    const titleEl = document.getElementById('tool-detail-title');
    const protoEl = document.getElementById('tool-detail-proto');
    const descEl = document.getElementById('tool-detail-desc');
    const schemaTable = document.getElementById('tool-schema-tbody');
    const exReqEl = document.getElementById('tool-example-req');
    const exResEl = document.getElementById('tool-example-res');

    function renderToolList(filter = '') {
      if (!rowsContainer) return;
      rowsContainer.innerHTML = '';

      Object.keys(TOOLS_DATA).forEach((key) => {
        const tool = TOOLS_DATA[key];
        if (filter && !tool.name.toLowerCase().includes(filter.toLowerCase()) && !tool.category.toLowerCase().includes(filter.toLowerCase())) {
          return;
        }

        const row = document.createElement('div');
        row.className = `tool-item-row ${state.activeTool === key ? 'active' : ''}`;
        row.innerHTML = `
          <div class="tool-name-wrap">
            <span class="tool-item-name">${escapeHtml(tool.name)}</span>
            <span class="tool-item-category">${escapeHtml(tool.category)}</span>
          </div>
          <span class="method-badge ${tool.method.toLowerCase()}">${tool.method}</span>
        `;

        row.addEventListener('click', () => {
          state.activeTool = key;
          document.querySelectorAll('.tool-item-row').forEach((r) => r.classList.remove('active'));
          row.classList.add('active');
          renderToolDetail(tool);
        });

        rowsContainer.appendChild(row);
      });
    }

    function renderToolDetail(tool) {
      if (titleEl) titleEl.innerText = tool.name;
      if (protoEl) protoEl.innerText = tool.protocol;
      if (descEl) descEl.innerText = tool.description;

      if (schemaTable) {
        schemaTable.innerHTML = '';
        tool.schema.forEach((param) => {
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td><code>${escapeHtml(param.param)}</code></td>
            <td><code>${escapeHtml(param.type)}</code></td>
            <td>${param.required ? '<span style="color:#ef4444;font-weight:700;">Yes</span>' : '<span style="color:#64748b;">No</span>'}</td>
            <td>${escapeHtml(param.desc)}</td>
          `;
          schemaTable.appendChild(tr);
        });
      }

      if (exReqEl) exReqEl.innerText = JSON.stringify(tool.exampleReq, null, 2);
      if (exResEl) exResEl.innerText = typeof tool.exampleRes === 'string' ? tool.exampleRes : JSON.stringify(tool.exampleRes, null, 2);
    }

    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        renderToolList(e.target.value);
      });
    }

    renderToolList();
    if (TOOLS_DATA[state.activeTool]) {
      renderToolDetail(TOOLS_DATA[state.activeTool]);
    }
  }

  // ===================================================================
  // INTEGRATION HUB & QUICKSTART TABS
  // ===================================================================
  function initIntegrationTabs() {
    const tabBtns = document.querySelectorAll('.integ-tab-btn');
    const tabContents = document.querySelectorAll('.integ-tab-content');

    tabBtns.forEach((btn) => {
      btn.addEventListener('click', () => {
        const tab = btn.getAttribute('data-tab');
        state.activeIntegTab = tab;

        tabBtns.forEach((b) => b.classList.remove('active'));
        tabContents.forEach((c) => c.classList.remove('active'));

        btn.classList.add('active');
        const activeContent = document.getElementById(`integ-content-${tab}`);
        if (activeContent) activeContent.classList.add('active');
      });
    });
  }

  // ===================================================================
  // FAQ ACCORDION
  // ===================================================================
  function initFaqAccordion() {
    const faqCards = document.querySelectorAll('.faq-card');
    faqCards.forEach((card) => {
      card.addEventListener('click', () => {
        const isOpen = card.classList.contains('open');
        faqCards.forEach((c) => c.classList.remove('open'));
        if (!isOpen) card.classList.add('open');
      });
    });
  }

  // ===================================================================
  // COPY TO CLIPBOARD
  // ===================================================================
  function initCopyButtons() {
    document.querySelectorAll('.copy-btn').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const targetId = btn.getAttribute('data-copy-target');
        let textToCopy = '';
        if (targetId) {
          const el = document.getElementById(targetId);
          if (el) textToCopy = el.innerText;
        } else {
          textToCopy = btn.getAttribute('data-copy-text') || '';
        }

        if (textToCopy) {
          navigator.clipboard.writeText(textToCopy).then(() => {
            const orig = btn.innerHTML;
            btn.innerHTML = '✓ Copied!';
            showToast('📋 Copied to clipboard!');
            setTimeout(() => {
              btn.innerHTML = orig;
            }, 2000);
          });
        }
      });
    });
  }

  // Toast System
  function showToast(message) {
    let container = document.querySelector('.toast-container');
    if (!container) {
      container = document.createElement('div');
      container.className = 'toast-container';
      document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.innerHTML = `<span>⚡</span><span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
})();
