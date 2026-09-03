"""Model Context Protocol (MCP) Server & ChatGPT Control Tools Tests."""

import json
import pytest
from app.mcp.server import process_json_rpc


@pytest.mark.asyncio
async def test_mcp_initialize():
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "chatgpt-client", "version": "1.0.0"},
        },
    }
    resp = await process_json_rpc(req)
    assert resp.error is None
    assert resp.result["protocolVersion"] == "2024-11-05"
    assert resp.result["serverInfo"]["name"] == "antigravity-bridge"
    assert "tools" in resp.result["capabilities"]


@pytest.mark.asyncio
async def test_mcp_tools_list():
    req = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {},
    }
    resp = await process_json_rpc(req)
    assert resp.error is None
    tools = resp.result["tools"]
    tool_names = [t["name"] for t in tools]

    # Verify ChatGPT Control Plane tools
    assert "list_projects" in tool_names
    assert "get_project" in tool_names
    assert "get_project_context" in tool_names
    assert "get_project_tree" in tool_names
    assert "list_agent_sessions" in tool_names
    assert "create_agent_session" in tool_names
    assert "send_agent_command" in tool_names
    assert "continue_agent_session" in tool_names
    assert "get_task_status" in tool_names
    assert "get_task_events" in tool_names
    assert "cancel_agent_session" in tool_names


@pytest.mark.asyncio
async def test_mcp_chatgpt_project_discovery(test_project, db_session):
    req = {
        "jsonrpc": "2.0",
        "id": 10,
        "method": "tools/call",
        "params": {
            "name": "list_projects",
            "arguments": {},
        },
    }
    resp = await process_json_rpc(req, db=db_session)
    assert resp.error is None
    assert resp.result["isError"] is False
    projects = json.loads(resp.result["content"][0]["text"])
    assert len(projects) >= 1
    assert projects[0]["project_id"] == test_project.id
    assert projects[0]["status"] == "authorized"


@pytest.mark.asyncio
async def test_mcp_chatgpt_project_tree_security(test_project, db_session):
    # Valid bounded tree request
    req = {
        "jsonrpc": "2.0",
        "id": 11,
        "method": "tools/call",
        "params": {
            "name": "get_project_tree",
            "arguments": {"project_id": test_project.id, "subpath": ""},
        },
    }
    resp = await process_json_rpc(req, db=db_session)
    assert resp.error is None
    assert resp.result["isError"] is False

    # Path traversal attack attempt: "../" outside workspace
    traversal_req = {
        "jsonrpc": "2.0",
        "id": 12,
        "method": "tools/call",
        "params": {
            "name": "get_project_tree",
            "arguments": {"project_id": test_project.id, "subpath": "../../Windows/System32"},
        },
    }
    trap_resp = await process_json_rpc(traversal_req, db=db_session)
    # Must be blocked and return error
    assert trap_resp.result["isError"] is True
    assert "traversal" in trap_resp.result["content"][0]["text"].lower() or "denied" in trap_resp.result["content"][0]["text"].lower()


@pytest.mark.asyncio
async def test_mcp_send_agent_command_and_continuation(test_project, db_session):
    # 1. Send Agent Command
    send_req = {
        "jsonrpc": "2.0",
        "id": 13,
        "method": "tools/call",
        "params": {
            "name": "send_agent_command",
            "arguments": {
                "project_id": test_project.id,
                "prompt": "Inspect codebase architecture.",
                "priority": "high",
            },
        },
    }
    send_resp = await process_json_rpc(send_req, db=db_session)
    assert send_resp.error is None
    assert send_resp.result["isError"] is False
    res_data = json.loads(send_resp.result["content"][0]["text"])
    assert "task_id" in res_data
    task_id = res_data["task_id"]

    # 2. Query Task Status
    status_req = {
        "jsonrpc": "2.0",
        "id": 14,
        "method": "tools/call",
        "params": {
            "name": "get_task_status",
            "arguments": {"task_id": task_id},
        },
    }
    stat_resp = await process_json_rpc(status_req, db=db_session)
    assert stat_resp.error is None
    assert stat_resp.result["isError"] is False
    stat_data = json.loads(stat_resp.result["content"][0]["text"])
    assert stat_data["task_id"] == task_id
