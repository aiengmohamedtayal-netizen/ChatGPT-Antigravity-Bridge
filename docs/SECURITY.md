# Security Architecture & Infrastructure Guide

The **ChatGPT × Antigravity Bridge** is designed as a developer infrastructure tool with enterprise-grade security practices.

---

## 1. Authentication & API Key Management

- **Cryptographic Key Generation**: API keys are generated using `secrets.token_urlsafe(32)` with an `agb_live_` prefix.
- **Hashed Storage**: Raw keys are never stored in the database. Only the **SHA-256** hash (`hashlib.sha256(raw_key).hexdigest()`) is persisted.
- **One-Time Display**: Keys are shown to the user or admin exactly once upon creation.
- **Constant-Time Comparison**: Key validation uses `secrets.compare_digest` to prevent timing attacks.

---

## 2. Secrets Encryption at Rest

- Sensitive connection credentials and provider tokens are encrypted using **Fernet (AES-GCM)** symmetric encryption (`app/core/security.py`).
- The encryption key is deterministically derived from `BRIDGE_SECRET_KEY` using SHA-256 base64.

---

## 3. Role-Based Access Control (RBAC)

API keys are bound to granular permission scopes:
- `tasks:create`: Can dispatch new tasks or continue sessions.
- `tasks:read`: Can poll status and view logs.
- `tasks:cancel`: Can abort running tasks.
- `projects:read`: Can inspect repository context.
- `projects:write`: Can create or update project workspaces.
- `admin`: Full administrative rights (key creation, provider switching, system settings).

---

## 4. Rate Limiting & Replay Protection

- **SlowAPI Token Bucket Limiter**: Prevents denial of service and API abuse (default: 120 req/min, task dispatch: 30 req/min).
- **Idempotency Keys**: Clients can supply an `Idempotency-Key` header with `POST /api/v1/tasks`. If a network retry occurs, the bridge deduplicates the submission and returns the existing task without duplicate execution.

---

## 5. Audit Logging

Every critical event is immutably logged into the `audit_logs` database table:
- Actor (API Key label)
- Action (`TASK_CREATE`, `TASK_CONTINUE`, `TASK_CANCEL`, `API_KEY_CREATE`, `API_KEY_REVOKE`)
- Target Resource ID
- Client IP Address
- Timestamp & Status
