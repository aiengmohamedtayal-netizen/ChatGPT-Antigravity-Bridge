"""Automated tests for Multi-Workspace REST API and MCP Dynamic Filesystem Tools."""

import json
import os
import pytest
from app.mcp.server import process_json_rpc
from app.services.workspace_service import workspace_service
from app.services.fs_service import fs_service


# =====================================================================
# REST API TESTS
# =====================================================================

def test_api_list_workspaces(client, admin_api_key):
    """Test GET /api/v1/workspaces lists all authorized workspaces."""
    resp = client.get("/api/v1/workspaces", headers={"X-API-Key": admin_api_key["raw_key"]})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2
    ids = [w["id"] for w in data]
    assert "proj_tool" in ids or "proj_default" in ids


def test_api_get_workspace_details(client, admin_api_key):
    """Test GET /api/v1/workspaces/{id} returns workspace metadata and preview."""
    workspaces = workspace_service.list_authorized_workspaces(enabled_only=True)
    target_id = workspaces[0].id
    resp = client.get(f"/api/v1/workspaces/{target_id}", headers={"X-API-Key": admin_api_key["raw_key"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == target_id
    assert "path" in data
    assert "preview_entries" in data


def test_api_workspace_file_lifecycle(client, admin_api_key):
    """Test writing, reading, listing, and deleting a file via REST API."""
    workspaces = [w for w in workspace_service.list_authorized_workspaces(enabled_only=True) if w.exists_on_disk]
    ws = workspaces[0]
    test_rel_path = "tmp_test_api_file.txt"
    headers = {"X-API-Key": admin_api_key["raw_key"]}

    # 1. Write file
    write_payload = {
        "path": test_rel_path,
        "content": "Hello Multi-Workspace Bridge!",
        "overwrite": True,
    }
    w_resp = client.post(f"/api/v1/workspaces/{ws.id}/file", json=write_payload, headers=headers)
    assert w_resp.status_code == 200
    assert w_resp.json()["success"] is True

    # 2. Read file
    r_resp = client.get(f"/api/v1/workspaces/{ws.id}/file?path={test_rel_path}", headers=headers)
    assert r_resp.status_code == 200
    assert r_resp.json()["content"] == "Hello Multi-Workspace Bridge!"

    # 3. List directory
    l_resp = client.get(f"/api/v1/workspaces/{ws.id}/files", headers=headers)
    assert l_resp.status_code == 200
    names = [e["name"] for e in l_resp.json()["entries"]]
    assert test_rel_path in names

    # 4. Search file
    s_resp = client.get(f"/api/v1/workspaces/{ws.id}/search?query={test_rel_path}", headers=headers)
    assert s_resp.status_code == 200
    assert s_resp.json()["total_matches"] >= 1

    # 5. Delete file without confirm should fail (400)
    d_fail = client.delete(f"/api/v1/workspaces/{ws.id}/file?path={test_rel_path}&confirm=false", headers=headers)
    assert d_fail.status_code == 400

    # 6. Delete file with confirm=true
    d_resp = client.delete(f"/api/v1/workspaces/{ws.id}/file?path={test_rel_path}&confirm=true", headers=headers)
    assert d_resp.status_code == 200
    assert d_resp.json()["success"] is True


def test_api_unauthorized_path_rejected(client, admin_api_key):
    """Test accessing unauthorized paths outside workspace returns 403 Forbidden."""
    headers = {"X-API-Key": admin_api_key["raw_key"]}
    workspaces = workspace_service.list_authorized_workspaces(enabled_only=True)
    ws_id = workspaces[0].id

    # Read attempt outside workspace
    resp = client.get(f"/api/v1/workspaces/{ws_id}/file?path=C:\\Windows\\win.ini", headers=headers)
    assert resp.status_code == 403
    assert "outside the authorized workspace roots" in resp.json()["detail"].lower()


# =====================================================================
# MCP TOOL TESTS
# =====================================================================

@pytest.mark.asyncio
async def test_mcp_list_workspaces(db_session):
    """Test list_workspaces MCP tool returns authorized workspace roots."""
    req = {
        "jsonrpc": "2.0",
        "id": 101,
        "method": "tools/call",
        "params": {
            "name": "list_workspaces",
            "arguments": {"enabled_only": True},
        },
    }
    resp = await process_json_rpc(req, db=db_session)
    assert resp.error is None
    assert resp.result.get("isError") is not True
    workspaces = json.loads(resp.result["content"][0]["text"])
    assert len(workspaces) >= 2


@pytest.mark.asyncio
async def test_mcp_get_workspace(db_session):
    """Test get_workspace MCP tool."""
    ws = workspace_service.list_authorized_workspaces(enabled_only=True)[0]
    req = {
        "jsonrpc": "2.0",
        "id": 102,
        "method": "tools/call",
        "params": {
            "name": "get_workspace",
            "arguments": {"workspace_id": ws.id},
        },
    }
    resp = await process_json_rpc(req, db=db_session)
    assert resp.error is None
    assert resp.result.get("isError") is not True
    data = json.loads(resp.result["content"][0]["text"])
    assert data["id"] == ws.id


@pytest.mark.asyncio
async def test_mcp_file_operations_lifecycle(db_session):
    """Test read_file, write_file, create_directory, move_file, delete_file via MCP."""
    ws = [w for w in workspace_service.list_authorized_workspaces(enabled_only=True) if w.exists_on_disk][0]
    test_file = "test_mcp_lifecycle.txt"
    moved_file = "test_mcp_lifecycle_renamed.txt"

    # 1. write_file
    w_req = {
        "jsonrpc": "2.0",
        "id": 103,
        "method": "tools/call",
        "params": {
            "name": "write_file",
            "arguments": {
                "workspace_id": ws.id,
                "path": test_file,
                "content": "MCP file content test 123",
                "overwrite": True,
            },
        },
    }
    w_resp = await process_json_rpc(w_req, db=db_session)
    assert w_resp.error is None
    assert w_resp.result.get("isError") is not True

    # 2. read_file
    r_req = {
        "jsonrpc": "2.0",
        "id": 104,
        "method": "tools/call",
        "params": {
            "name": "read_file",
            "arguments": {"workspace_id": ws.id, "path": test_file},
        },
    }
    r_resp = await process_json_rpc(r_req, db=db_session)
    assert r_resp.error is None
    read_data = json.loads(r_resp.result["content"][0]["text"])
    assert read_data["content"] == "MCP file content test 123"

    # 3. move_file
    m_req = {
        "jsonrpc": "2.0",
        "id": 105,
        "method": "tools/call",
        "params": {
            "name": "move_file",
            "arguments": {
                "workspace_id": ws.id,
                "source_path": test_file,
                "target_path": moved_file,
            },
        },
    }
    m_resp = await process_json_rpc(m_req, db=db_session)
    assert m_resp.error is None
    assert m_resp.result.get("isError") is not True

    # 4. delete_file without confirm=True must fail
    d_fail_req = {
        "jsonrpc": "2.0",
        "id": 106,
        "method": "tools/call",
        "params": {
            "name": "delete_file",
            "arguments": {"workspace_id": ws.id, "path": moved_file, "confirm": False},
        },
    }
    d_fail_resp = await process_json_rpc(d_fail_req, db=db_session)
    assert d_fail_resp.result["isError"] is True

    # 5. delete_file with confirm=True
    d_ok_req = {
        "jsonrpc": "2.0",
        "id": 107,
        "method": "tools/call",
        "params": {
            "name": "delete_file",
            "arguments": {"workspace_id": ws.id, "path": moved_file, "confirm": True},
        },
    }
    d_ok_resp = await process_json_rpc(d_ok_req, db=db_session)
    assert d_ok_resp.error is None
    assert d_ok_resp.result.get("isError") is not True


@pytest.mark.asyncio
async def test_mcp_unauthorized_read_blocked(db_session):
    """Test that reading unauthorized system path via MCP returns error."""
    req = {
        "jsonrpc": "2.0",
        "id": 108,
        "method": "tools/call",
        "params": {
            "name": "read_file",
            "arguments": {"path": "C:\\Windows\\System32\\drivers\\etc\\hosts"},
        },
    }
    resp = await process_json_rpc(req, db=db_session)
    assert resp.result["isError"] is True
    assert "outside the authorized workspace roots" in resp.result["content"][0]["text"].lower()


@pytest.mark.asyncio
async def test_mcp_send_agent_command_multi_workspace(db_session):
    """Test send_agent_command with workspace_id directing execution to specific workspace."""
    workspaces = workspace_service.list_authorized_workspaces(enabled_only=True)
    target_ws = workspaces[-1]  # Pick another workspace

    cmd_req = {
        "jsonrpc": "2.0",
        "id": 109,
        "method": "tools/call",
        "params": {
            "name": "send_agent_command",
            "arguments": {
                "workspace_id": target_ws.id,
                "prompt": "Inspect current repository setup.",
            },
        },
    }
    resp = await process_json_rpc(cmd_req, db=db_session)
    assert resp.error is None
    assert resp.result.get("isError") is not True
    data = json.loads(resp.result["content"][0]["text"])
    assert data["status"] == "queued"
    assert data["workspace_path"].lower() == target_ws.path.lower()
