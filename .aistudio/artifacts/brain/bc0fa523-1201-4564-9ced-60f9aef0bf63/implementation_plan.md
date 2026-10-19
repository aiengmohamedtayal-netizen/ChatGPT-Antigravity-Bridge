# Agensi.io Agent Skill Packaging — ChatGPT × Antigravity Bridge

Package the ChatGPT × Antigravity Bridge MCP server into a security-compliant, ready-to-publish Agensi.io Agent Skill (`SKILL.md` standard) that enables Claude Code, Cursor, GitHub Copilot, Windsurf, OpenAI Codex CLI, and ChatGPT to orchestrate multi-workspace coding tasks and bounded filesystem operations over MCP.

### User Review & Critical Decisions

> [!IMPORTANT]
> The skill package is designed to pass Agensi.io's 8-point automated security scan on the first submission by strictly separating pure markdown/JSON instruction assets from executable binaries, using explicit placeholder tokens for credentials, and restricting network references to documented local and Cloudflare tunnel endpoints.

- **Confirmed Decision 1 — Marketplace Pricing Strategy**: Configured as a **Paid Single Tier ($9 one-time developer license)** in the marketplace metadata (yielding $6.30 creator payout per sale under Agensi's 70/30 split), positioned as a production-ready multi-workspace orchestration bridge.
- **Confirmed Decision 2 — Universal Client Compatibility**: Includes ready-to-paste MCP configuration templates and trigger rules for **Claude Code, Cursor, ChatGPT (Custom GPT & Desktop MCP), GitHub Copilot / VS Code, Windsurf, and OpenAI Codex CLI** across both `stdio` and remote `SSE` transports.
- **Confirmed Decision 3 — Repository Organization**: Organized inside a dedicated skill directory alongside an automated packaging utility that validates frontmatter and builds the submission-ready `.zip` archive without modifying core MCP server logic.
- **Runtime Port Alignment**: Also ensures the local FastAPI entrypoint can bind cleanly in the preview environment on port 3000 when launched by the platform runner while preserving existing defaults.

---

### 1. Overview & Core Concept

- **What It Does**: Transforms the ChatGPT × Antigravity Bridge into a portable, progressive-disclosure Agent Skill that teaches external AI coding agents **when** and **how** to discover authorized local workspaces, inspect files safely, dispatch autonomous coding sessions to Google Antigravity, and stream task verification telemetry.
- **Target Audience / Persona**: Developers, software architects, and AI power users who plan architectures in high-reasoning models (ChatGPT, Claude, Cursor, Copilot) and want frictionless, security-bounded execution across multiple local repositories without manual copy-pasting.
- **Key Value**: Eliminates context fragmentation between cloud/desktop AI planners and local execution engines while guaranteeing strict workspace path isolation, session continuity (`session_id` reuse), and automated self-healing build/test verification.

---

### 2. User Experience & Visual Design

- **Key User Flows**:
  1. **Skill Installation Flow**: End-user downloads the skill archive from Agensi.io and drops the skill folder into their agent's skills directory (e.g., `~/.claude/skills/`, `.cursor/skills/`, or `.github/skills/`) and pastes the 5-line MCP server snippet (`stdio` or `SSE`).
  2. **Progressive Disclosure & Trigger Flow**: When the user asks their agent to inspect a local project, run cross-workspace refactors, or delegate implementation to Antigravity, the agent matches the YAML frontmatter description and loads the full skill instruction set.
  3. **Multi-Turn Execution Flow**: The agent calls workspace discovery tools first, dispatches or continues a stateful Antigravity session, monitors progress via task status/events, and reports verified build results back to the user.
  4. **Creator Packaging Flow**: Running the packaging utility validates Agensi.io's 8-point security rules (no secrets, no binaries, valid YAML frontmatter, matching folder slug) and outputs a clean `.zip` archive ready for the Agensi Creator Dashboard.

- **Visual Identity & Documentation Presentation**:
  - *Aesthetic Direction*: Utilitarian, high-clarity technical documentation following KISS principles with scannable decision tables, copy-pasteable configuration blocks, and zero filler prose.
  - *Typography & Hierarchy*: Structured Markdown hierarchy using clear YAML frontmatter, tabular tool decision matrices, and Mermaid sequence/architecture diagrams in project documentation.
  - *Component Styling & Layout*: Progressive-disclosure layout where the top-level skill file stays compact for fast LLM token ingestion, delegating deep client setup snippets and exhaustive parameter schemas to reference documents.

- **Interactive Feedback & Verification**:
  - The packaging script provides immediate console validation checks for all 8 Agensi.io security scan criteria before emitting the final `.zip` bundle.

---

### 3. Key Product Decisions & Trade-Offs

- **Decision 1: Progressive-Disclosure Skill Architecture (`SKILL.md` + `references/`)**
  - *Chosen Approach*: Keep the primary skill instruction file focused on core trigger heuristics, decision workflows, and guardrails, while placing client-specific MCP configs and detailed JSON-RPC/tool parameter references in dedicated reference modules.
  - *Why*: Minimizes context window token consumption when agents load the skill, improving instruction adherence and latency across Claude Code, Cursor, and Copilot.
  - *Alternatives Considered*: Putting all 25+ MCP tool schemas and 6 client setup guides into a single monolithic markdown file, which bloats prompt tokens and degrades agent tool-selection accuracy.

- **Decision 2: Dual-Transport MCP Configuration (`stdio` + `SSE`)**
  - *Chosen Approach*: Provide both local `stdio` invocation configs (for local desktop agents like Claude Code, Cursor, VS Code Copilot, Windsurf, and Codex CLI) and remote `SSE` tunnel configs (for ChatGPT Desktop and Custom GPT Actions).
  - *Why*: Allows local IDE agents to spawn the bridge over `stdio` with zero network configuration while preserving remote cloud orchestration for ChatGPT via Cloudflare Quick Tunnels.
  - *Alternatives Considered*: Documenting only `SSE` over HTTP, which requires users to manually manage a background daemon even when working locally inside Cursor or Claude Code.

- **Decision 3: Automated 8-Point Pre-Flight Validator & Zip Builder**
  - *Chosen Approach*: Include a lightweight Python packaging utility that audits the skill folder for hardcoded secrets, binary files, dangerous shell patterns, and frontmatter schema compliance before generating the `.zip` archive.
  - *Why*: Guarantees frictionless approval during Agensi.io's automated security scan and human review.

---

### 4. Technical Architecture & Data Strategy *(Technical Reference)*

- **Architecture & Component Diagram**:

```
┌────────────────────────────────────────────────────────────────────────────┐
│                   AGENSI.IO AGENT SKILL PACKAGE (.zip)                     │
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │ Primary Skill Entrypoint (YAML Frontmatter + Prompt Instructions)    │  │
│  │  • Trigger Conditions (WHEN to invoke vs. native IDE tools)          │  │
│  │  • 4-Step Execution Protocol (Discover → Context → Dispatch → Poll)  │  │
│  │  • Session Continuity Rules (session_id reuse via continue tool)     │  │
│  │  • Security & Boundary Guardrails (confirm=True, workspace scoping)  │  │
│  └──────────────────┬───────────────────────────────────┬───────────────┘  │
│                     │ Progressive Disclosure            │                  │
│                     ▼                                   ▼                  │
│  ┌─────────────────────────────────────┐ ┌──────────────────────────────┐  │
│  │ Client MCP Config Reference         │ │ MCP Tools & Workflow Matrix  │  │
│  │  • Claude Code & Cursor (stdio/SSE) │ │  • 12 Workspace & FS Tools   │  │
│  │  • GitHub Copilot / VS Code         │ │  • 13 Control Plane Tools    │  │
│  │  • Windsurf & OpenAI Codex CLI      │ │  • 3 Callback Telemetry Tools│  │
│  │  • ChatGPT Desktop & Custom GPT     │ │  • Error & Recovery Patterns │  │
│  └─────────────────────────────────────┘ └──────────────────────────────┘  │
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │ Marketplace Listing Specification ($9 Single-Tier Metadata)          │  │
│  │  • Title, Tagline, Pricing ($9), Category, Tags, Setup Checklist     │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────┬──────────────────────────────────────┘
                                      │
                                      ▼
┌────────────────────────────────────────────────────────────────────────────┐
│            CHATGPT × ANTIGRAVITY BRIDGE MCP SERVER (FastAPI)               │
│                                                                            │
│   [MCP Stdio Runner] ◄───► [JSON-RPC 2.0 Dispatcher] ◄───► [MCP SSE :8000] │
│                                        │                                   │
│                    ┌───────────────────┴───────────────────┐               │
│                    ▼                                       ▼               │
│       [Workspace Boundary Guard]             [Task Orchestrator & Queue]   │
│       (Canonical Path Isolation)             (Antigravity Session Engine)  │
└────────────────────────────────────────────────────────────────────────────┘
```

- **Data Model & Skill Metadata Schema**:
  - **Skill Frontmatter (`SKILL.md`)**:
    - `name`: `"chatgpt-antigravity-bridge"` (strictly matches parent folder in archive)
    - `description`: Action-oriented trigger summary specifying multi-workspace filesystem operations, Google Antigravity task delegation, session continuity, and automated build/test self-healing.
    - `version`: `"1.0.0"`
    - `license`: `"MIT"`
  - **Marketplace Listing Metadata**:
    - Captures storefront fields required by Agensi.io Creator Dashboard: product name, short summary, long description, `$9.00` USD one-time license pricing, target agent compatibility matrix, categories (`DevOps & Automation`, `IDE & Coding Workflows`, `MCP Servers`), and buyer onboarding instructions.

- **Interactive Component & Workflow Mapping**:
  - **Workflow 1 — Direct Bounded Filesystem Inspection & Editing**:
    - *Trigger*: User asks agent to read, search, or edit files across one or more authorized local repositories (`workspaces.json`).
    - *Sequence*: `list_workspaces` → `get_file_tree` / `search_files` → `read_file` → `write_file` (with canonical path boundary validation).
  - **Workflow 2 — Autonomous Antigravity Task Delegation & Self-Healing**:
    - *Trigger*: User requests complex multi-file implementation, refactoring, or test execution delegated to Google Antigravity.
    - *Sequence*: `list_projects` → `get_project_context` → `send_agent_command` (returns `task_id` and `session_id`) → poll `get_task_status` & `get_task_events` until `completed` or `failed`.
  - **Workflow 3 — Stateful Multi-Turn Session Continuation**:
    - *Trigger*: User gives follow-up instructions on a previously executed task.
    - *Sequence*: Agent reuses `session_id` via `continue_agent_session` instead of spawning a cold session, preserving full conversation history in Antigravity's brain directory.
  - **Workflow 4 — Automated Packaging & 8-Point Security Verification**:
    - *Trigger*: Developer runs the skill packaging script to build the Agensi.io `.zip` upload artifact.
    - *Sequence*: Verifies YAML frontmatter (`name` and `description`), scans all files for forbidden binaries or secret patterns, validates relative links, and writes `dist/chatgpt-antigravity-bridge-skill.zip`.
