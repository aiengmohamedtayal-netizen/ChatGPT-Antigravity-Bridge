# Architecture Documentation

## 1. System Topology

```
┌─────────────────────────────────────────────────────────────┐
│                    ChatGPT                                  │
│         (System Architect / Lead Orchestrator)              │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTPS / OpenAPI 3.1 REST
                               ▼
┌─────────────────────────────────────────────────────────────┐
│             ChatGPT × Antigravity Bridge Control Plane       │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  API Gateway & Security Layer                       │   │
│   │  • Bearer Token Auth (SHA-256)                      │   │
│   │  • RBAC Scopes Enforcement                          │   │
│   │  • SlowAPI Rate Limiting (Token Bucket)             │   │
│   │  • Idempotency & Audit Logger                       │   │
│   └──────────────────────────┬──────────────────────────┘   │
│                              │                              │
│   ┌──────────────────────────▼──────────────────────────┐   │
│   │  Task Orchestration Engine                          │   │
│   │  • Priority Queue Worker (Urgent > High > Normal)   │   │
│   │  • State Machine (Queued -> Running -> Completed)   │   │
│   │  • Conversational Session Continuation Engine       │   │
│   │  • Project Context Manager                          │   │
│   └──────────────────────────┬──────────────────────────┘   │
│                              │                              │
│   ┌──────────────────────────▼──────────────────────────┐   │
│   │  Provider / Adapter Layer                           │   │
│   │  • AntigravitySDKProvider (Primary)                 │   │
│   │  • AntigravityCliProvider (Fallback)                │   │
│   │  • SimulatedAgentProvider (CI / Staging)            │   │
│   │  • ClaudeCodeProvider / GeminiCliProvider (Ext)     │   │
│   └──────────────┬───────────────────────────▲──────────┘   │
│                  │                           │              │
│                  │ Antigravity SDK           │ MCP Protocol │
│                  ▼                           │              │
│   ┌──────────────────────────┐   ┌───────────┴──────────┐   │
│   │   Google Antigravity     │   │  Bridge MCP Server   │   │
│   │   • Agent & Skills       │◄──┤  (Remote & Stdio)    │   │
│   │   • Code Modification    │   │  • Context & Tools   │   │
│   │   • Session Persistence  │   │  • Artifact Store    │   │
│   └──────────────────────────┘   └──────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## 2. Core Interfaces

- **`BaseAgentProvider`**:
  - `check_health()`
  - `create_session(workspace_path, session_id)`
  - `execute_task(task_id, session_id, prompt, workspace_path, context, is_continuation)`
  - `cancel_task(task_id, session_id)`

- **`TaskOrchestrator`**:
  - Priority queue scheduling
  - Background asynchronous task loop
  - Session continuation linkage: reuses `session_id` and appends preceding context
  - Cancellation propagation

- **`ExecutionLogger`**:
  - Structured database persistence in `execution_logs` table
  - Real-time pub/sub distribution to SSE (`/api/v1/tasks/{id}/events`) and WebSockets (`/ws/tasks/{id}`)
