"""Real Acceptance Test: Testing the ChatGPT MCP Control Plane against the Live Local Antigravity Environment."""

import json
import time
import httpx

BASE_URL = "http://127.0.0.1:8000"


def rpc_call(client, method, params=None, req_id=1):
    payload = {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
        "params": params or {},
    }
    resp = client.post(f"{BASE_URL}/mcp/messages", json=payload, timeout=30.0)
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
    print("STARTING REAL ACCEPTANCE TEST: CHATGPT <-> ANTIGRAVITY GATEWAY")
    print("================================================================")

    with httpx.Client() as client:
        # Step A: Initialize MCP session
        init_res = rpc_call(client, "initialize")
        print(f"[OK] Step A: MCP Handshake: Server '{init_res['serverInfo']['name']}' v{init_res['serverInfo']['version']}")

        # Step B: List Tools
        tools_res = rpc_call(client, "tools/list")
        tool_names = [t["name"] for t in tools_res["tools"]]
        print(f"[OK] Step B: Discovered {len(tool_names)} MCP Tools: {', '.join(tool_names[:6])}...")

        # Step C: list_projects
        is_err, projects_raw = tool_call(client, "list_projects")
        assert not is_err, f"list_projects error: {projects_raw}"
        projects = json.loads(projects_raw)
        print(f"[OK] Step C: list_projects() returned {len(projects)} authorized workspace(s):")
        for p in projects:
            print(f"    - ID: {p['project_id']} | Name: {p['name']} | Path: {p['workspace_path']}")
        target_project_id = projects[0]["project_id"]

        # Step D: get_project_context
        is_err, ctx_raw = tool_call(client, "get_project_context", {"project_id": target_project_id})
        assert not is_err, f"get_project_context error: {ctx_raw}"
        ctx = json.loads(ctx_raw)
        print(f"[OK] Step D: get_project_context('{target_project_id}') - Tracked files: {ctx['tracked_files_count']}")

        # Step E: Security Boundary Test (Attempt path traversal)
        is_err, trap_raw = tool_call(client, "get_project_tree", {"project_id": target_project_id, "subpath": "../../Windows/System32"})
        assert is_err, "Security violation: Path traversal was not blocked!"
        print(f"[SECURE] Step E: Security Boundary Verified: Traversal attack was rejected: {trap_raw[:60]}...")

        # Step F: create_agent_session (Real Antigravity Session via agentapi.bat)
        is_err, session_raw = tool_call(client, "create_agent_session", {"project_id": target_project_id, "title": "Acceptance Test"})
        assert not is_err, f"create_agent_session error: {session_raw}"
        sess_data = json.loads(session_raw)
        session_id = sess_data["session_id"]
        print(f"[OK] Step F: Real Antigravity Agent Session Created: ID = {session_id}")

        # Step G: send_agent_command (Prompt 1)
        prompt1 = "Inspect this project and report its current architecture."
        is_err, cmd1_raw = tool_call(client, "send_agent_command", {
            "project_id": target_project_id,
            "session_id": session_id,
            "prompt": prompt1,
            "priority": "high",
        })
        assert not is_err, f"send_agent_command error: {cmd1_raw}"
        cmd1_data = json.loads(cmd1_raw)
        task1_id = cmd1_data["task_id"]
        print(f"[OK] Step G: Prompt 1 Dispatched to Antigravity: Task ID = {task1_id}")

        # Step H: Monitor Execution
        time.sleep(3)
        is_err, stat1_raw = tool_call(client, "get_task_status", {"task_id": task1_id})
        assert not is_err
        stat1 = json.loads(stat1_raw)
        print(f"[OK] Step H: Task 1 State: {stat1['status']} | Output Summary: {stat1['summary'][:90]}...")

        # Step I: continue_agent_session (Prompt 2 on SAME session)
        prompt2 = "Now implement the highest-priority improvement you identified."
        is_err, cont_raw = tool_call(client, "continue_agent_session", {
            "session_id": session_id,
            "prompt": prompt2,
            "priority": "high",
        })
        assert not is_err, f"continue_agent_session error: {cont_raw}"
        cont_data = json.loads(cont_raw)
        task2_id = cont_data["task_id"]
        print(f"[OK] Step I: Continuation Dispatched on SAME session: Task ID = {task2_id} (Session: {cont_data['session_id']})")
        assert cont_data["session_id"] == session_id, "Session ID must match!"

        # Step J: Verify Session History
        is_err, sess_hist_raw = tool_call(client, "get_agent_session", {"session_id": session_id})
        assert not is_err
        sess_hist = json.loads(sess_hist_raw)
        print(f"[OK] Step J: Session History Confirmed: {sess_hist['total_tasks']} linked tasks in session '{session_id}'")

        print("================================================================")
        print("ALL ACCEPTANCE CRITERIA VERIFIED SUCCESSFULLY AGAINST LIVE GATEWAY!")
        print("================================================================")


if __name__ == "__main__":
    main()
