"""Workspace boundary security, canonical path validation, and traversal protection."""

import os
from pathlib import Path
from typing import Optional, Tuple
from app.core.errors import AuthorizationError, NotFoundError


class WorkspaceBoundaryGuard:
    """Enforces strict filesystem isolation and path-traversal protection."""

    ERROR_ACCESS_DENIED = "Access denied: this path is outside the authorized workspace roots."
    ERROR_WORKSPACE_UNAVAILABLE = "Workspace unavailable: the configured workspace path does not exist."

    @staticmethod
    def canonicalize(path: str) -> str:
        """Resolve absolute, normalized, symlink-free canonical path."""
        try:
            if not path or not isinstance(path, str):
                return ""
            # os.path.realpath resolves symlinks and junctions on Windows
            return os.path.realpath(os.path.abspath(os.path.normpath(path)))
        except Exception:
            return ""

    @classmethod
    def is_containment_valid(cls, target_path: str, root_path: str) -> bool:
        """Check if target_path is strictly within root_path using canonical containment."""
        try:
            common = os.path.commonpath([target_path, root_path])
            # Windows file paths are case-insensitive
            return common.lower() == root_path.lower()
        except (ValueError, Exception):
            # Cross-drive on Windows (e.g. C: vs D:)
            return False

    @classmethod
    def validate_path(
        cls,
        target_path: str,
        workspace_id_or_root: Optional[str] = None,
    ) -> Tuple[str, str]:
        """
        Validate that target_path belongs to an authorized workspace.
        If workspace_id_or_root is given, validates against that specific workspace.
        Otherwise validates against ANY enabled authorized workspace root.
        Returns (canonical_target_path, matching_workspace_root).
        """
        from app.services.workspace_service import workspace_service

        if not target_path or not isinstance(target_path, str):
            raise AuthorizationError(cls.ERROR_ACCESS_DENIED)

        # Immediate traversal pattern rejection
        if ".." in target_path.replace("\\", "/").split("/"):
            raise AuthorizationError(cls.ERROR_ACCESS_DENIED)

        # 1. Specific workspace specified
        if workspace_id_or_root:
            ws = workspace_service.get_workspace(workspace_id_or_root)
            raw_root = ws.path if ws else workspace_id_or_root
            canonical_root = cls.canonicalize(raw_root)

            if not canonical_root or not os.path.exists(canonical_root):
                raise NotFoundError(cls.ERROR_WORKSPACE_UNAVAILABLE)

            # If target is relative, resolve relative to root
            if not os.path.isabs(target_path):
                candidate = os.path.join(canonical_root, target_path.lstrip("/\\"))
            else:
                candidate = target_path

            canonical_target = cls.canonicalize(candidate)
            if not canonical_target or not cls.is_containment_valid(canonical_target, canonical_root):
                raise AuthorizationError(cls.ERROR_ACCESS_DENIED)

            return canonical_target, canonical_root

        # 2. No specific workspace: check if it falls within ANY authorized workspace
        canonical_target = cls.canonicalize(target_path)
        if not canonical_target:
            raise AuthorizationError(cls.ERROR_ACCESS_DENIED)

        for ws in workspace_service.list_authorized_workspaces(enabled_only=True):
            canon_root = cls.canonicalize(ws.path)
            if canon_root and os.path.exists(canon_root):
                if cls.is_containment_valid(canonical_target, canon_root):
                    return canonical_target, canon_root

        raise AuthorizationError(cls.ERROR_ACCESS_DENIED)

    @classmethod
    def validate_path_in_workspace(cls, target_path: str, workspace_root: str) -> str:
        """
        Backward-compatible check: ensure target_path resides strictly within workspace_root.
        Returns the safe canonical path or raises AuthorizationError / NotFoundError.
        """
        canonical_target, _ = cls.validate_path(target_path, workspace_root)
        return canonical_target

    @classmethod
    def sanitize_relative_subpath(cls, subpath: Optional[str], workspace_root: str) -> str:
        """Sanitize a relative subpath within an authorized workspace."""
        if not subpath or subpath in (".", "/", "\\"):
            return cls.canonicalize(workspace_root)

        if ".." in subpath:
            raise AuthorizationError("Path traversal ('..') is strictly prohibited.")

        combined = os.path.join(workspace_root, subpath.lstrip("/\\"))
        return cls.validate_path_in_workspace(combined, workspace_root)


boundary_guard = WorkspaceBoundaryGuard()
