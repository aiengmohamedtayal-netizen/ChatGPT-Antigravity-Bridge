"""
Tests for Autonomous Workspace Provisioning, Project Initialization Tool, and Boundary Security.
"""

import json
import os
import shutil
import pytest
from app.mcp.server import process_json_rpc
from app.security.boundary import boundary_guard
from app.services.workspace_service import workspace_service
from app.core.errors import AuthorizationError, NotFoundError, BadRequestError


@pytest.fixture(autouse=True)
def preserve_workspaces_config():
    """Preserve workspaces.json across test execution to avoid test pollution."""
    config_path = os.path.join(os.getcwd(), "workspaces.json")
    backup_content = None
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            backup_content = f.read()
    yield
    if backup_content is not None:
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(backup_content)
    workspace_service.reload()


@pytest.fixture
def temp_authorized_parent(tmp_path):
    """Register a temporary directory as an authorized root workspace for testing."""
    root_dir = str(tmp_path / "test_root")
    os.makedirs(root_dir, exist_ok=True)
    ws = workspace_service.register_workspace(
        path=root_dir,
        name="Test Authorized Root",
        workspace_id="test_authorized_root",
        save_to_config=False,
    )
    yield root_dir, ws
    # Teardown
    workspace_service._workspaces.pop("test_authorized_root", None)
    if os.path.exists(root_dir):
        shutil.rmtree(root_dir, ignore_errors=True)


def test_auto_provision_workspace_on_the_fly(temp_authorized_parent):
    """Verify that requesting a nonexistent path within an authorized root auto-provisions with mkdir -p."""
    root_dir, root_ws = temp_authorized_parent
    target_subpath = os.path.join(root_dir, "auto_created_app", "sub_module")
    assert not os.path.exists(target_subpath)

    # Calling get_workspace with auto_provision=True should create and register it
    ws = workspace_service.get_workspace(target_subpath, auto_provision=True)
    assert ws is not None
    assert os.path.exists(target_subpath)
    assert ws.exists_on_disk is True
    assert ws.path.lower() == target_subpath.lower()

    # Clean up created workspace from in-memory dict
    workspace_service._workspaces.pop(ws.id, None)


def test_boundary_security_blocks_restricted_system_directories(temp_authorized_parent):
    """Verify system directories (C:\\Windows, C:\\Program Files, /etc) cannot be provisioned or initialized."""
    restricted_targets = [
        r"C:\Windows\System32\new_project",
        r"C:\Program Files\new_app",
        r"C:\Program Files (x86)\exploit",
        r"C:\Windows",
    ]
    for restricted in restricted_targets:
        # 1. auto_provision must return None
        prov = workspace_service.auto_provision_workspace(restricted)
        assert prov is None

        # 2. init_project_workspace must raise AuthorizationError
        with pytest.raises(AuthorizationError):
            workspace_service.init_project_workspace(path=restricted)


def test_boundary_security_blocks_unauthorized_roots():
    """Verify paths on un-authorized drives or directories cannot be provisioned."""
    unauthorized_path = r"Z:\completely_unauthorized_drive\project"
    prov = workspace_service.auto_provision_workspace(unauthorized_path)
    assert prov is None

    with pytest.raises(AuthorizationError):
        workspace_service.init_project_workspace(path=unauthorized_path)


def test_init_project_workspace_scaffolds(temp_authorized_parent):
    """Verify init_project_workspace creates directory, .gitignore, README.md, AGENTS.md, and python files."""
    root_dir, root_ws = temp_authorized_parent
    new_project_path = os.path.join(root_dir, "my_python_service")

    res = workspace_service.init_project_workspace(
        path=new_project_path,
        name="My Python Service",
        description="A scalable Python microservice.",
        instructions="Always write pytest unit tests and type annotations.",
        scaffold="python",
        init_git=True,
    )

    assert res["success"] is True
    assert res["name"] == "My Python Service"
    assert os.path.isdir(new_project_path)

    # Verify created scaffold files
    assert os.path.exists(os.path.join(new_project_path, ".gitignore"))
    assert os.path.exists(os.path.join(new_project_path, "README.md"))
    assert os.path.exists(os.path.join(new_project_path, "AGENTS.md"))
    assert os.path.exists(os.path.join(new_project_path, "pyproject.toml"))
    assert os.path.exists(os.path.join(new_project_path, "main.py"))

    # Verify AGENTS.md contents
    with open(os.path.join(new_project_path, "AGENTS.md"), "r", encoding="utf-8") as f:
        content = f.read()
    assert "Always write pytest unit tests" in content

    # Clean up
    workspace_service._workspaces.pop(res["workspace_id"], None)


@pytest.mark.asyncio
async def test_mcp_create_workspace_tool(temp_authorized_parent, db_session):
    """Verify create_workspace MCP tool execution end-to-end via JSON-RPC."""
    root_dir, root_ws = temp_authorized_parent
    target_path = os.path.join(root_dir, "mcp_web_app")

    req = {
        "jsonrpc": "2.0",
        "id": "req-init-1",
        "method": "tools/call",
        "params": {
            "name": "create_workspace",
            "arguments": {
                "path": target_path,
                "name": "MCP Web App",
                "description": "Frontend UI created via MCP",
                "scaffold": "web",
                "init_git": False,
            },
        },
    }
    resp = await process_json_rpc(req, db=db_session)
    assert resp.error is None
    assert resp.result is not None
    res_data = json.loads(resp.result["content"][0]["text"])
    assert res_data["success"] is True
    assert res_data["workspace_id"] in workspace_service._workspaces
    assert os.path.exists(os.path.join(target_path, "index.html"))
    assert os.path.exists(os.path.join(target_path, "style.css"))

    # Clean up
    workspace_service._workspaces.pop(res_data["workspace_id"], None)


@pytest.mark.asyncio
async def test_mcp_create_agent_session_auto_provisions(temp_authorized_parent, db_session):
    """Verify create_agent_session on a non-existent path within an authorized root automatically provisions it."""
    root_dir, root_ws = temp_authorized_parent
    unregistered_path = os.path.join(root_dir, "auto_agent_project")
    assert not os.path.exists(unregistered_path)

    req = {
        "jsonrpc": "2.0",
        "id": "req-session-auto-1",
        "method": "tools/call",
        "params": {
            "name": "create_agent_session",
            "arguments": {
                "project_id": unregistered_path,
                "title": "Autonomous Initialization Test",
            },
        },
    }
    resp = await process_json_rpc(req, db=db_session)
    assert resp.error is None
    assert resp.result is not None
    data = json.loads(resp.result["content"][0]["text"])
    assert "session_id" in data
    assert data["status"] == "ready"
    assert os.path.exists(unregistered_path)

    # Clean up
    workspace_service._workspaces.pop(data["project_id"], None)


@pytest.mark.asyncio
async def test_mcp_send_agent_command_auto_provisions(temp_authorized_parent, db_session):
    """Verify send_agent_command on a new path auto-provisions and queues the task."""
    root_dir, root_ws = temp_authorized_parent
    brand_new_path = os.path.join(root_dir, "command_target_app")
    assert not os.path.exists(brand_new_path)

    req = {
        "jsonrpc": "2.0",
        "id": "req-cmd-auto-1",
        "method": "tools/call",
        "params": {
            "name": "send_agent_command",
            "arguments": {
                "project_id": brand_new_path,
                "prompt": "Create an initial Hello World script",
            },
        },
    }
    resp = await process_json_rpc(req, db=db_session)
    assert resp.error is None
    assert resp.result is not None
    data = json.loads(resp.result["content"][0]["text"])
    assert data["status"] == "queued"
    assert os.path.exists(brand_new_path)

    # Clean up
    workspace_service._workspaces.pop(data["project_id"], None)


def test_rest_api_workspace_init(client, admin_api_key, temp_authorized_parent):
    """Verify REST API POST /api/v1/workspaces/init creates and registers a project."""
    root_dir, root_ws = temp_authorized_parent
    api_target = os.path.join(root_dir, "api_node_service")

    payload = {
        "path": api_target,
        "name": "API Node Service",
        "description": "Express REST backend",
        "scaffold": "node",
        "init_git": False,
    }
    resp = client.post(
        "/api/v1/workspaces/init",
        json=payload,
        headers={"X-API-Key": admin_api_key["raw_key"]},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["success"] is True
    assert data["name"] == "API Node Service"
    assert os.path.exists(os.path.join(api_target, "package.json"))
    assert os.path.exists(os.path.join(api_target, "src", "index.js"))

    # Clean up
    workspace_service._workspaces.pop(data["workspace_id"], None)
