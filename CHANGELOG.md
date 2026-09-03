# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-09-03

### Added
- **FastAPI Control Plane Gateway**: Central control plane exposing REST endpoints for project discovery, session lifecycle, and task dispatching.
- **ChatGPT Custom Actions Integration**: OpenAPI 3.1 schema endpoint at `/api/v1/chatgpt/openapi.json` for web, iOS, and Android Custom GPTs.
- **Model Context Protocol (MCP) 2024-11-05 Server**: Full SSE transport at `/mcp/sse` and message handling at `/mcp/messages` supporting 12 ChatGPT control plane tools and 4 Antigravity callback tools.
- **Antigravity Multi-Turn Session Continuity**: Context-preserving task continuation via `POST /api/v1/tasks/{id}/continue`.
- **Priority Queue Worker**: Asynchronous background queue engine with prioritization (`urgent`, `high`, `normal`, `low`).
- **Filesystem Boundary Guard**: Canonical symlink-free path validation blocking directory traversal attacks (`../`) outside the authorized workspace.
- **Pluggable Agent Providers**: Pluggable provider architecture with `antigravity_real` (local language server via `agentapi.bat`), `antigravity_sdk`, and `simulated` (in-memory mock for standalone testing and CI).
- **Pure Headless Architecture**: Streamlined headless service with root metadata discovery, zero frontend overhead, and direct OpenAPI/MCP orchestration.
- **Automated Cloudflare Quick Tunnel Helper**: Cross-platform launcher with automatic official binary detection/downloading for zero-port-forwarding ingress.
- **Security & Authentication**: Bearer API key authentication with SHA-256 constant-time hashing, Fernet AES credential encryption, and SlowAPI rate limiting.
- **Automated Pytest Suite**: 21 unit and integration tests covering security, task queue, MCP protocol, and end-to-end ChatGPT workflows.
- **GitHub Community Standards**: MIT License, GitHub Actions CI matrix, CodeQL security scanning, Dependabot configuration, and issue/PR templates.
