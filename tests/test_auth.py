"""Authentication, Authorization, and Encryption Unit Tests."""

from datetime import datetime, timedelta, timezone
from app.core.security import (
    encrypt_secret,
    decrypt_secret,
    generate_api_key,
    hash_api_key,
    verify_api_key,
)
from app.models.api_key import ApiKey, ApiScope


def test_encryption_roundtrip():
    secret = "sk-super-sensitive-token-12345!@#"
    encrypted = encrypt_secret(secret)
    assert encrypted != secret
    decrypted = decrypt_secret(encrypted)
    assert decrypted == secret


def test_api_key_verification():
    raw_key, hashed, prefix = generate_api_key()
    assert raw_key.startswith("agb_live_")
    assert verify_api_key(raw_key, hashed) is True
    assert verify_api_key("wrong_key", hashed) is False


def test_missing_api_key_rejected(client):
    response = client.get("/api/v1/tasks")
    assert response.status_code == 401
    assert response.json()["code"] == "MISSING_API_KEY"


def test_invalid_api_key_rejected(client):
    headers = {"Authorization": "Bearer agb_live_invalidkey12345"}
    response = client.get("/api/v1/tasks", headers=headers)
    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_API_KEY"


def test_scope_enforcement_rejected(client, test_project, read_only_api_key):
    # read_only_api_key has only TASKS_READ, not TASKS_CREATE
    headers = {"Authorization": f"Bearer {read_only_api_key['raw_key']}"}
    payload = {
        "project_id": test_project.id,
        "prompt": "Create something unauthorized",
    }
    response = client.post("/api/v1/tasks", json=payload, headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "INSUFFICIENT_SCOPE"


def test_admin_api_key_allowed(client, test_project, admin_api_key):
    headers = {"Authorization": f"Bearer {admin_api_key['raw_key']}"}
    payload = {
        "project_id": test_project.id,
        "prompt": "Create authorized task",
    }
    response = client.post("/api/v1/tasks", json=payload, headers=headers)
    assert response.status_code == 201
    assert response.json()["status"] == "queued"
