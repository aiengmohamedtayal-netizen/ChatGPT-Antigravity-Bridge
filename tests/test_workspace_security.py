"""Automated tests for path security, canonical boundaries, and multi-workspace validation."""

import os
import pytest
from app.security.boundary import boundary_guard
from app.services.workspace_service import workspace_service
from app.core.errors import AuthorizationError, NotFoundError


def test_canonical_path_normalization():
    """Verify that canonicalize resolves real, absolute, normalized paths."""
    cwd = os.getcwd()
    # Test with redundant slashes and dots
    messy_path = os.path.join(cwd, ".", "app", "..", "app")
    canonical = boundary_guard.canonicalize(messy_path)
    expected = os.path.join(cwd, "app")
    assert canonical.lower() == expected.lower()


def test_windows_casing_and_separators():
    """Verify Windows paths with forward vs backward slashes and uppercase/lowercase letters."""
    cwd = os.getcwd()
    forward_slash_path = cwd.replace("\\", "/") + "/app/main.py"
    target, root = boundary_guard.validate_path(forward_slash_path)
    assert os.path.exists(target)
    assert boundary_guard.is_containment_valid(target, root)


def test_path_traversal_rejection():
    """Verify that directory traversal sequences are strictly rejected."""
    cwd = os.getcwd()
    traversal_paths = [
        os.path.join(cwd, "..", "..", "Windows"),
        os.path.join(cwd, "app", "..", "..", "Windows", "System32"),
        "../../etc/passwd",
        "..\\..\\Windows",
        "../" * 5 + "boot.ini",
    ]
    for bad_path in traversal_paths:
        with pytest.raises(AuthorizationError) as exc_info:
            boundary_guard.validate_path(bad_path)
        assert boundary_guard.ERROR_ACCESS_DENIED in str(exc_info.value.detail)


def test_unauthorized_absolute_paths():
    """Verify that unauthorized absolute system paths outside workspace roots are rejected."""
    system_paths = [
        r"C:\Windows\System32\calc.exe",
        r"C:\Program Files",
        r"C:\Users",
    ]
    for sys_path in system_paths:
        with pytest.raises(AuthorizationError) as exc_info:
            boundary_guard.validate_path(sys_path)
        assert boundary_guard.ERROR_ACCESS_DENIED in str(exc_info.value.detail)


def test_nonexistent_workspace_rejection():
    """Verify that querying a nonexistent workspace returns the required unavailable message."""
    nonexistent_root = r"D:\completely_fake_workspace_dir_999"
    with pytest.raises(NotFoundError) as exc_info:
        boundary_guard.validate_path("some_file.txt", workspace_id_or_root=nonexistent_root)
    assert boundary_guard.ERROR_WORKSPACE_UNAVAILABLE in str(exc_info.value.detail)


def test_restricted_drive_root_and_system_dirs():
    """Verify that bare drive roots and system folders cannot be registered as workspaces."""
    assert workspace_service.is_restricted_path("C:\\\\") is True
    assert workspace_service.is_restricted_path("D:\\\\") is True
    assert workspace_service.is_restricted_path("C:\\\\Windows") is True
    assert workspace_service.is_restricted_path("C:\\\\Program Files") is True
    assert workspace_service.is_restricted_path(os.getcwd()) is False


def test_multiple_workspaces_containment():
    """Verify that paths within any authorized workspace succeed and resolve the correct root."""
    workspaces = workspace_service.list_authorized_workspaces(enabled_only=True)
    assert len(workspaces) >= 2, "Expected at least 2 authorized workspaces in test environment"

    for ws in workspaces:
        if ws.exists_on_disk:
            target, matched_root = boundary_guard.validate_path(ws.path)
            assert target.lower() == ws.path.lower()
            assert matched_root.lower() == ws.path.lower()


def test_cross_workspace_containment_failure():
    """When a specific workspace is requested, paths outside that specific workspace must be rejected."""
    workspaces = [w for w in workspace_service.list_authorized_workspaces(enabled_only=True) if w.exists_on_disk]
    if len(workspaces) >= 2:
        ws_a = workspaces[0]
        ws_b = workspaces[1]

        # Valid in its own workspace
        boundary_guard.validate_path(ws_a.path, workspace_id_or_root=ws_a.id)

        # Accessing ws_b while specifying workspace_id=ws_a must be denied
        with pytest.raises(AuthorizationError) as exc_info:
            boundary_guard.validate_path(ws_b.path, workspace_id_or_root=ws_a.id)
        assert boundary_guard.ERROR_ACCESS_DENIED in str(exc_info.value.detail)
