"""Task Management, Lifecycle, and Idempotency Tests."""

import uuid


def test_create_task_success(client, test_project, admin_api_key):
    headers = {"Authorization": f"Bearer {admin_api_key['raw_key']}"}
    payload = {
        "project_id": test_project.id,
        "prompt": "Build user signup route with password hashing",
        "priority": "high",
    }
    response = client.post("/api/v1/tasks", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["project_id"] == test_project.id
    assert data["prompt"] == payload["prompt"]
    assert data["priority"] == "high"
    assert data["status"] == "queued"
    assert "id" in data


def test_create_task_invalid_project(client, admin_api_key):
    headers = {"Authorization": f"Bearer {admin_api_key['raw_key']}"}
    payload = {
        "project_id": "non_existent_project",
        "prompt": "Some task",
    }
    response = client.post("/api/v1/tasks", json=payload, headers=headers)
    assert response.status_code == 404
    assert response.json()["code"] == "PROJECT_NOT_FOUND"


def test_task_idempotency(client, test_project, admin_api_key):
    headers = {
        "Authorization": f"Bearer {admin_api_key['raw_key']}",
        "Idempotency-Key": f"idemp_{uuid.uuid4().hex}",
    }
    payload = {
        "project_id": test_project.id,
        "prompt": "Create unique billing webhook",
    }
    # First request
    res1 = client.post("/api/v1/tasks", json=payload, headers=headers)
    assert res1.status_code == 201
    task1_id = res1.json()["id"]

    # Replay identical request with same idempotency key
    res2 = client.post("/api/v1/tasks", json=payload, headers=headers)
    assert res2.status_code == 201
    task2_id = res2.json()["id"]

    # Should return the exact same task
    assert task1_id == task2_id


def test_cancel_task(client, test_project, admin_api_key):
    headers = {"Authorization": f"Bearer {admin_api_key['raw_key']}"}
    # Create task
    res = client.post(
        "/api/v1/tasks",
        json={"project_id": test_project.id, "prompt": "Long running task"},
        headers=headers,
    )
    task_id = res.json()["id"]

    # Cancel task
    cancel_res = client.post(f"/api/v1/tasks/{task_id}/cancel", headers=headers)
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "cancelled"
