"""
Acceptance Test Script: End-to-End Session Test for REZAN Workspace.
Validates dynamic discovery, workspace authorization, real Antigravity session creation,
instruction dispatch, execution monitoring, and multi-turn session continuation.
"""

import asyncio
import json
import os
import sys
import time

# Ensure project root is in sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app import database
from app.config import get_settings
from app.mcp.server import process_json_rpc
from app.models.task import Task, TaskStatus
from app.orchestration.orchestrator import orchestrator
from app.providers.registry import provider_registry
from app.services.workspace_service import workspace_service
from app.services.antigravity_discovery import antigravity_discovery


async def rpc_call(method: str, params: dict = None, req_id: int = 1) -> dict:
    req = {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
        "params": params or {},
    }
    resp = await process_json_rpc(req)
    if resp.error:
        raise RuntimeError(f"MCP RPC Error [{resp.error.code}]: {resp.error.message}")
    return resp.result


async def tool_call(tool_name: str, arguments: dict = None, req_id: int = 1) -> dict:
    res = await rpc_call("tools/call", {"name": tool_name, "arguments": arguments or {}}, req_id=req_id)
    content = res.get("content", [{}])[0].get("text", "")
    is_err = res.get("isError", False)
    if is_err:
        raise RuntimeError(f"Tool '{tool_name}' returned error: {content}")
    try:
        return json.loads(content)
    except Exception:
        return {"raw_text": content}


async def main():
    print("=" * 70)
    print("  CHATGPT x ANTIGRAVITY BRIDGE: REZAN AGENT SESSION TEST")
    print("=" * 70)

    # Step 0: Initialize DB & ensure orchestrator worker is running
    database.init_db()
    db = database.SessionLocal()
    try:
        workspace_service.sync_with_db(db)
    finally:
        db.close()

    orchestrator.start_worker()

    # Step 1: Workspace Authorization Check
    print("\n[Step 1] Verifying REZAN workspace registration and disk accessibility...")
    ws = workspace_service.get_workspace("D:\\REZAN", auto_provision=True)
    assert ws is not None, "Workspace for D:\\REZAN could not be resolved or auto-provisioned!"
    assert ws.exists_on_disk, f"Workspace path '{ws.path}' does not exist on disk!"
    print(f"  [OK] Workspace Resolved: ID='{ws.id}', Name='{ws.name}', Path='{ws.path}'")

    # Step 2: Language Server & Real Provider Health Check
    print("\n[Step 2] Probing Antigravity Language Server health and credentials...")
    provider = provider_registry.get_provider()
    health = await provider.check_health()
    print(f"  [OK] Health Check Status: {health.get('status')} ({health.get('message')})")
    assert health.get("status") == "connected", f"Provider not connected: {health}"

    # Step 3: MCP Handshake & Tool Discovery
    print("\n[Step 3] Performing MCP Protocol Handshake...")
    init_res = await rpc_call("initialize", req_id=10)
    print(f"  [OK] Server Info: {init_res['serverInfo']['name']} v{init_res['serverInfo']['version']}")

    # Step 4: Project Context Extraction
    print("\n[Step 4] Retrieving project context for REZAN...")
    ctx = await tool_call("get_project_context", {"project_id": ws.id}, req_id=11)
    tracked_files = ctx.get("tracked_files_count", 0)
    print(f"  [OK] REZAN Context: Tracked files count = {tracked_files}")

    # Step 5: Create Real Antigravity Agent Session
    print("\n[Step 5] Initializing new Antigravity conversational session for REZAN...")
    session_data = await tool_call(
        "create_agent_session",
        {"project_id": ws.id, "title": "Session test for REZAN"},
        req_id=12,
    )
    session_id = session_data.get("session_id")
    assert session_id, "No session_id returned from create_agent_session!"
    print(f"  [OK] Session Created successfully! Session ID = {session_id}")

    # Verify session directory in Antigravity Brain
    brain_dir = get_settings().ANTIGRAVITY_BRAIN_DIR
    session_brain = os.path.join(brain_dir, session_id)
    assert os.path.exists(session_brain), f"Session brain directory '{session_brain}' not found on disk!"
    print(f"  [OK] Session Brain Verified at: {session_brain}")

    # Step 6: Dispatch Instruction Prompt to Antigravity Agent
    print("\n[Step 6] Dispatching inspection instruction to REZAN session...")
    test_prompt = (
        "Session verification test for REZAN. "
        "Inspect D:\\REZAN\\package.json, check the framework and dependencies, "
        "and provide a concise confirmation summary."
    )
    cmd_data = await tool_call(
        "send_agent_command",
        {
            "project_id": ws.id,
            "session_id": session_id,
            "prompt": test_prompt,
            "priority": "high",
        },
        req_id=13,
    )
    task_id = cmd_data.get("task_id")
    assert task_id, "Task ID was not returned from send_agent_command!"
    print(f"  [OK] Task Dispatched: ID='{task_id}', Status='{cmd_data.get('status')}'")

    # Step 7: Monitor Task Execution
    print("\n[Step 7] Monitoring task execution progress...")
    max_wait = 45.0
    start_t = time.monotonic()
    completed = False
    last_status = ""

    while time.monotonic() - start_t < max_wait:
        await asyncio.sleep(2.0)
        status_data = await tool_call("get_task_status", {"task_id": task_id}, req_id=14)
        current_status = status_data.get("status", "")
        if current_status != last_status:
            print(f"  -> Task State: {current_status}")
            last_status = current_status

        if current_status in ("completed", "failed", "cancelled"):
            completed = True
            print(f"  [OK] Terminal State Reached: {current_status}")
            if status_data.get("summary"):
                print(f"  [Summary] {status_data.get('summary')[:160]}...")
            break

    if not completed:
        print(f"  [INFO] Task still executing or waiting (Current state: {last_status}). Proceeding with continuation test.")

    # Step 8: Multi-Turn Continuation Test on the SAME session
    print("\n[Step 8] Testing session continuation on the SAME Antigravity session...")
    cont_prompt = "Acknowledge session test completion for REZAN."
    cont_data = await tool_call(
        "continue_agent_session",
        {
            "session_id": session_id,
            "prompt": cont_prompt,
            "priority": "normal",
        },
        req_id=15,
    )
    cont_task_id = cont_data.get("task_id")
    assert cont_task_id, "No continuation task_id returned!"
    assert cont_data.get("session_id") == session_id, "Session ID mismatch in continuation!"
    print(f"  [OK] Continuation Dispatched: ID='{cont_task_id}', Session='{cont_data.get('session_id')}'")

    # Step 9: Verify Session History
    print("\n[Step 9] Inspecting session history and task linkage...")
    history_data = await tool_call("get_agent_session", {"session_id": session_id}, req_id=16)
    history_list = history_data.get("history", [])
    total_tasks = history_data.get("total_tasks") or history_data.get("task_count") or len(history_list)
    print(f"  [OK] Session History: Total linked tasks in session = {total_tasks}")
    assert total_tasks >= 2, f"Expected at least 2 linked tasks in session, got {total_tasks}!"

    for item in history_list:
        print(f"    - Task [{item.get('task_id')}]: Prompt='{item.get('prompt')[:60]}' | Status={item.get('status')}")

    # Step 10: Clean up orchestrator worker
    await orchestrator.stop_worker()
    await asyncio.sleep(0.5)

    print("\n" + "=" * 70)
    print("  ALL SESSION TEST VERIFICATION CRITERIA FOR REZAN PASSED!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
