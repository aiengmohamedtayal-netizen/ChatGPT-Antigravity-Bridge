"""End-to-End Primary Workflow Test: ChatGPT -> Bridge -> Antigravity -> Continuation."""

import time


def test_complete_chatgpt_workflow(client, test_project, admin_api_key):
    headers = {"Authorization": f"Bearer {admin_api_key['raw_key']}"}

    # Step 1: ChatGPT discovers action schema
    schema_res = client.get("/api/v1/chatgpt/openapi.json")
    assert schema_res.status_code == 200
    assert "paths" in schema_res.json()

    # Step 2: ChatGPT inspects project context
    ctx_res = client.get(f"/api/v1/projects/{test_project.id}/context", headers=headers)
    assert ctx_res.status_code == 200
    assert ctx_res.json()["name"] == test_project.name

    # Step 3: ChatGPT dispatches initial feature prompt
    task1_payload = {
        "project_id": test_project.id,
        "prompt": "Implement authentication using Supabase.",
        "priority": "high",
    }
    task1_res = client.post("/api/v1/tasks", json=task1_payload, headers=headers)
    assert task1_res.status_code == 201
    task1_id = task1_res.json()["id"]

    # Poll until completed (simulated provider runs with 0.01s step delay)
    completed = False
    for _ in range(50):
        time.sleep(0.05)
        poll_res = client.get(f"/api/v1/tasks/{task1_id}", headers=headers)
        if poll_res.status_code == 200 and poll_res.json()["status"] == "completed":
            completed = True
            break
    assert completed, "Task 1 should complete successfully"

    task1_data = poll_res.json()
    assert task1_data["antigravity_response"] is not None
    assert len(task1_data["logs"]) > 0

    # Step 4: ChatGPT reviews output and sends conversational follow-up
    task2_payload = {
        "prompt": "Now add password reset.",
    }
    task2_res = client.post(f"/api/v1/tasks/{task1_id}/continue", json=task2_payload, headers=headers)
    assert task2_res.status_code == 201
    task2_id = task2_res.json()["id"]
    assert task2_res.json()["parent_task_id"] == task1_id

    # Poll continuation until completed
    cont_completed = False
    for _ in range(50):
        time.sleep(0.05)
        poll_cont = client.get(f"/api/v1/tasks/{task2_id}", headers=headers)
        if poll_cont.status_code == 200 and poll_cont.json()["status"] == "completed":
            cont_completed = True
            break
    assert cont_completed, "Continuation task should complete successfully"

    task2_data = poll_cont.json()
    assert task2_data["status"] == "completed"
    assert task2_data["parent_task_id"] == task1_id
    assert task2_data["session_id"] == task1_data["session_id"]
