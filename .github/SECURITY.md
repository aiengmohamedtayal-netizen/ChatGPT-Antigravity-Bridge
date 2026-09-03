# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

Security issues are taken seriously. If you discover a vulnerability or security flaw in the ChatGPT x Antigravity Bridge:

1. **Do not open a public GitHub issue.**
2. Please report the issue privately by emailing the maintainer at **aiengmohamedtayal@gmail.com** or by opening a private GitHub Security Advisory.
3. Include detailed steps to reproduce the issue, along with any relevant payload examples or logs.
4. You will receive an acknowledgment within 48 hours, followed by an assessment and patch schedule.

## Security Design Principles

- **Zero Inbound Port Forwarding**: The gateway runs strictly on localhost (127.0.0.1:8000) and uses authenticated outbound tunnels for remote traffic.
- **Path Canonicalization**: All workspace path interactions are validated against WorkspaceBoundaryGuard to block traversal attacks (../).
- **Constant-Time Verification**: API tokens are hashed with SHA-256 and evaluated via secrets.compare_digest.
