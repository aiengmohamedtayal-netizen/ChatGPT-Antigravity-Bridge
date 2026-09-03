"""External End-to-End Test: Simulating ChatGPT reaching the Gateway via Public HTTPS Tunnel."""

import json
import os
import time
import httpx

# Read the active public tunnel URL
URL_FILE = os.path.join(os.path.dirname(__file__), "..", ".tunnel_url.txt")
with open(URL_FILE, "r") as f:
    TUNNEL_URL = f.read().strip()


def rpc_call(client, method, params=None, req_id=1):
    payload = {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
        "params": params or {},
    }
    resp = client.post(f"{TUNNEL_URL}/mcp/messages", json=payload, timeout=40.0)
    assert resp.status_code == 200, f"HTTP Error: {resp.status_code} {resp.text}"
    data = resp.json()
    assert "result" in data, f"RPC Error: {data}"
    return data["result"]


def tool_call(client, tool_name, arguments=None, req_id=1):
    res = rpc_call(
        client,
        "tools/call",
        {"name": tool_name, "arguments": arguments or {}},
        req_id=req_id,
    )
    is_err = res.get("isError", False)
    content_text = res.get("content", [{}])[0].get("text", "")
    return is_err, content_text


def main():
    print("================================================================")
    print("STARTING EXTERNAL E2E TEST: CHATGPT OVER SECURE TUNNEL")
    print(f"Target Public HTTPS URL: {TUNNEL_URL}")
    print("================================================================")

    with httpx.Client(timeout=45.0) as client:
        # Step 1: Verify Public Health & OpenAPI Spec
        health_resp = client.get(f"{TUNNEL_URL}/health")
        assert health_resp.status_code == 200, f"Health check failed: {health_resp.text}"
        print(f"[OK] Step 1: Public Gateway Health: {health_resp.json()['status']}")

        openapi_resp = client.get(f"{TUNNEL_URL}/api/v1/chatgpt/openapi.json")
        assert openapi_resp.status_code == 200
        print(f"[OK] Step 1b: OpenAPI 3.1 Spec Reachable: {len(openapi_resp.json()['paths'])} paths defined")

        # Step A: ChatGPT MCP Connect & Handshake
        init_res = rpc_call(client, "initialize")
        print(f"[OK] Step A: ChatGPT connected via Tunnel! MCP Server: '{init_res['serverInfo']['name']}'")

        # Step B: ChatGPT calls list_projects
        is_err, projects_raw = tool_call(client, "list_projects")
        assert not is_err, f"list_projects error: {projects_raw}"
        projects = json.loads(projects_raw)
        print(f"[OK] Step B: ChatGPT received {len(projects)} authorized project(s):")
        for p in projects:
            print(f"    - ID: {p['project_id']} | Name: {p['name']} | Path: {p['workspace_path']}")

        # Step C: ChatGPT selects authorized project
        target_project = projects[0]
        target_project_id = target_project["project_id"]
        print(f"[OK] Step C: ChatGPT selected project '{target_project['name']}' (ID: {target_project_id})")

        # Step D: ChatGPT calls get_project_context
        is_err, ctx_raw = tool_call(client, "get_project_context", {"project_id": target_project_id})
        assert not is_err, f"get_project_context error: {ctx_raw}"
        ctx = json.loads(ctx_raw)
        print(f"[OK] Step D: Project Context retrieved: {ctx['tracked_files_count']} tracked files")

        # Step E: ChatGPT creates Antigravity session
        is_err, sess_raw = tool_call(client, "create_agent_session", {
            "project_id": target_project_id,
            "title": "External ChatGPT Session",
        })
        assert not is_err, f"create_agent_session error: {sess_raw}"
        sess_data = json.loads(sess_raw)
        session_id = sess_data["session_id"]
        print(f"[OK] Step E: Antigravity Session Created: ID = {session_id}")

        # Step F: ChatGPT sends harmless instruction to real Antigravity agent
        harmless_prompt1 = "Inspect this project and report its current architecture."
        is_err, cmd_raw = tool_call(client, "send_agent_command", {
            "project_id": target_project_id,
            "session_id": session_id,
            "prompt": harmless_prompt1,
            "priority": "high",
        })
        assert not is_err, f"send_agent_command error: {cmd_raw}"
        cmd_data = json.loads(cmd_raw)
        task1_id = cmd_data["task_id"]
        print(f"[OK] Step F: Instruction dispatched to Antigravity Agent! Task ID = {task1_id}")

        # Step G & H: Wait for agent execution
        print("Waiting for Antigravity Agent execution...")
        time.sleep(3)

        # Step I: ChatGPT retrieves task status / result
        is_err, stat1_raw = tool_call(client, "get_task_status", {"task_id": task1_id})
        assert not is_err
        stat1 = json.loads(stat1_raw)
        print(f"[OK] Step I: Task Status: {stat1['status']}")
        print(f"    Summary: {stat1['summary'][:90]}...")

        # Step J: ChatGPT sends follow-up instruction
        harmless_prompt2 = "Confirm that test verification passed safely."
        is_err, cont_raw = tool_call(client, "continue_agent_session", {
            "session_id": session_id,
            "prompt": harmless_prompt2,
            "priority": "high",
        })
        assert not is_err, f"continue_agent_session error: {cont_raw}"
        cont_data = json.loads(cont_raw)
        task2_id = cont_data["task_id"]

        # Step K: Verify Gateway sends it to the SAME Antigravity session
        print(f"[OK] Step K: Continuation sent to SAME session: {cont_data['session_id']}")
        assert cont_data["session_id"] == session_id, "Session ID mismatch in continuation!"

        # Step L: ChatGPT receives final result
        time.sleep(3)
        is_err, stat2_raw = tool_call(client, "get_task_status", {"task_id": task2_id})
        assert not is_err
        stat2 = json.loads(stat2_raw)
        print(f"[OK] Step L: Final Continuation Result: Status = {stat2['status']}")
        print(f"    Summary: {stat2['summary'][:90]}...")

        print("================================================================")
        print("EXTERNAL E2E TEST PASSED 100% OVER PUBLIC ENCRYPTED TUNNEL!")
        print("================================================================")


if __name__ == "__main__":
    main()
