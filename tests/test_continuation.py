"""Multi-Turn Conversational Session Continuation Tests."""

import time


def test_session_continuation_linkage(client, test_project, admin_api_key):
    headers = {"Authorization": f"Bearer {admin_api_key['raw_key']}"}

    # 1. Create parent task
    parent_payload = {
        "project_id": test_project.id,
        "prompt": "Implement authentication using Supabase.",
    }
    parent_res = client.post("/api/v1/tasks", json=parent_payload, headers=headers)
    assert parent_res.status_code == 201
    parent_id = parent_res.json()["id"]

    # Give orchestrator worker a brief moment to assign session ID
    time.sleep(0.1)

    # 2. Continue the session
    continue_payload = {
        "prompt": "Now add password reset.",
    }
    cont_res = client.post(f"/api/v1/tasks/{parent_id}/continue", json=continue_payload, headers=headers)
    assert cont_res.status_code == 201
    child_data = cont_res.json()

    # 3. Verify continuation invariants
    assert child_data["parent_task_id"] == parent_id
    assert child_data["project_id"] == test_project.id
    assert child_data["prompt"] == continue_payload["prompt"]
    assert child_data["status"] == "queued"
