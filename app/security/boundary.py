"""Workspace boundary security, canonical path validation, and traversal protection."""

import os
from pathlib import Path
from typing import Optional
from app.core.errors import AuthorizationError, NotFoundError


class WorkspaceBoundaryGuard:
    """Enforces strict filesystem isolation and path-traversal protection."""

    @staticmethod
    def canonicalize(path: str) -> str:
        """Resolve absolute, normalized, symlink-free canonical path."""
        try:
            return os.path.realpath(os.path.abspath(os.path.normpath(path)))
        except Exception:
            return ""

    @classmethod
    def validate_path_in_workspace(cls, target_path: str, workspace_root: str) -> str:
        """
        Ensure target_path resides strictly within workspace_root.
        Returns the safe canonical path or raises AuthorizationError.
        """
        canonical_root = cls.canonicalize(workspace_root)
        if not canonical_root or not os.path.exists(canonical_root):
            raise NotFoundError(f"Workspace root '{workspace_root}' does not exist on disk.")

        canonical_target = cls.canonicalize(target_path)
        if not canonical_target:
            raise AuthorizationError("Invalid or unresolvable path.")

        # Check if canonical_root is a prefix of canonical_target
        try:
            common = os.path.commonpath([canonical_target, canonical_root])
            if common.lower() != canonical_root.lower():
                raise AuthorizationError(
                    f"Access Denied: Path '{target_path}' escapes authorized workspace boundary."
                )
        except ValueError:
            # Different drives on Windows (e.g. C: vs D:)
            raise AuthorizationError(
                f"Access Denied: Path '{target_path}' is on an unauthorized drive."
            )

        return canonical_target

    @classmethod
    def sanitize_relative_subpath(cls, subpath: Optional[str], workspace_root: str) -> str:
        """Sanitize a relative subpath within an authorized workspace."""
        if not subpath or subpath in (".", "/", "\\"):
            return cls.canonicalize(workspace_root)

        # Reject obvious traversal attempts upfront
        if ".." in subpath:
            raise AuthorizationError("Path traversal ('..') is strictly prohibited.")

        combined = os.path.join(workspace_root, subpath.lstrip("/\\"))
        return cls.validate_path_in_workspace(combined, workspace_root)


boundary_guard = WorkspaceBoundaryGuard()
