"""Dynamic Filesystem Operations Service with strict boundary validation."""

from datetime import datetime, timezone
import fnmatch
import logging
import os
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional, Tuple

from app.security.boundary import boundary_guard
from app.services.workspace_service import workspace_service
from app.core.errors import AuthorizationError, NotFoundError, BadRequestError

logger = logging.getLogger(__name__)

# Default file size reading limit (1 MB)
DEFAULT_MAX_READ_BYTES = 1_000_000
# Skip binary / large noise extensions by default in text search
DEFAULT_EXCLUDED_DIRS = {".git", "node_modules", ".venv", "__pycache__", "dist", "build", ".next"}


class FilesystemService:
    """Provides safe, boundary-enforced filesystem operations for authorized workspaces."""

    def __init__(self):
        self.boundary = boundary_guard
        self.workspaces = workspace_service

    def list_workspaces(self, enabled_only: bool = True) -> List[Dict[str, Any]]:
        """List all authorized workspaces with filesystem metadata."""
        workspaces = self.workspaces.list_authorized_workspaces(enabled_only=enabled_only)
        results = []
        for ws in workspaces:
            exists = bool(ws.path and os.path.isdir(ws.path))
            file_count = 0
            if exists:
                try:
                    # Quick top-level count
                    file_count = len(os.listdir(ws.path))
                except Exception:
                    file_count = 0

            results.append({
                "id": ws.id,
                "name": ws.name,
                "path": ws.path,
                "enabled": ws.enabled,
                "description": ws.description,
                "exists_on_disk": exists,
                "top_level_entries_count": file_count,
            })
        return results

    def get_workspace(self, workspace_id_or_path: str) -> Dict[str, Any]:
        """Get details and metadata for a specific workspace."""
        ws = self.workspaces.get_workspace(workspace_id_or_path)
        if not ws:
            raise NotFoundError(f"Workspace '{workspace_id_or_path}' not found in authorized workspaces.")

        exists = bool(ws.path and os.path.isdir(ws.path))
        tree_preview = []
        if exists:
            try:
                for entry in sorted(os.listdir(ws.path))[:20]:
                    full_p = os.path.join(ws.path, entry)
                    tree_preview.append({
                        "name": entry,
                        "is_dir": os.path.isdir(full_p),
                        "size": os.path.getsize(full_p) if os.path.isfile(full_p) else None,
                    })
            except Exception:
                pass

        return {
            "id": ws.id,
            "name": ws.name,
            "path": ws.path,
            "enabled": ws.enabled,
            "description": ws.description,
            "instructions": ws.instructions,
            "exists_on_disk": exists,
            "preview_entries": tree_preview,
        }

    def list_directory(
        self,
        path: Optional[str] = None,
        workspace_id: Optional[str] = None,
        show_hidden: bool = False,
    ) -> Dict[str, Any]:
        """List directory contents within an authorized workspace."""
        target = path or ""
        # If no path specified and workspace specified, default to workspace root
        if not target and workspace_id:
            ws = self.workspaces.get_workspace(workspace_id)
            if not ws:
                raise NotFoundError(f"Workspace '{workspace_id}' not found.")
            target = ws.path

        canon_path, root = self.boundary.validate_path(target, workspace_id_or_root=workspace_id)

        if not os.path.exists(canon_path):
            raise NotFoundError(f"Path '{path}' does not exist.")

        if not os.path.isdir(canon_path):
            raise BadRequestError(f"Path '{path}' is a file, not a directory.")

        entries = []
        try:
            for item in sorted(os.listdir(canon_path)):
                if not show_hidden and item.startswith("."):
                    continue

                full_item_path = os.path.join(canon_path, item)
                is_dir = os.path.isdir(full_item_path)
                try:
                    stat = os.stat(full_item_path)
                    size = stat.st_size if not is_dir else None
                    mtime = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
                except Exception:
                    size = None
                    mtime = None

                entries.append({
                    "name": item,
                    "path": full_item_path,
                    "relative_path": os.path.relpath(full_item_path, root),
                    "is_dir": is_dir,
                    "size_bytes": size,
                    "modified_at": mtime,
                })
        except PermissionError:
            raise AuthorizationError(f"Operating system permission denied accessing directory '{path}'.")

        return {
            "directory": canon_path,
            "workspace_root": root,
            "total_entries": len(entries),
            "entries": entries,
        }

    def read_file(
        self,
        path: str,
        workspace_id: Optional[str] = None,
        max_bytes: int = DEFAULT_MAX_READ_BYTES,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Safely read text content of a file within an authorized workspace."""
        canon_path, root = self.boundary.validate_path(path, workspace_id_or_root=workspace_id)

        if not os.path.exists(canon_path):
            raise NotFoundError(f"File '{path}' does not exist.")

        if os.path.isdir(canon_path):
            raise BadRequestError(f"Path '{path}' is a directory, not a file.")

        total_size = os.path.getsize(canon_path)

        try:
            with open(canon_path, "rb") as f:
                if offset > 0:
                    f.seek(offset)
                raw_data = f.read(max_bytes)

            content = raw_data.decode("utf-8", errors="replace")
            is_truncated = (offset + len(raw_data)) < total_size

            return {
                "path": canon_path,
                "relative_path": os.path.relpath(canon_path, root),
                "workspace_root": root,
                "content": content,
                "size_bytes": total_size,
                "bytes_read": len(raw_data),
                "offset": offset,
                "is_truncated": is_truncated,
            }
        except PermissionError:
            raise AuthorizationError(f"Operating system permission denied reading file '{path}'.")

    def write_file(
        self,
        path: str,
        content: str,
        workspace_id: Optional[str] = None,
        overwrite: bool = True,
    ) -> Dict[str, Any]:
        """Safely create or overwrite a file within an authorized workspace."""
        canon_path, root = self.boundary.validate_path(path, workspace_id_or_root=workspace_id)

        if os.path.exists(canon_path) and not overwrite:
            raise BadRequestError(f"File '{path}' already exists and overwrite is set to False.")

        if os.path.exists(canon_path) and os.path.isdir(canon_path):
            raise BadRequestError(f"Cannot overwrite directory '{path}' with a file.")

        # Ensure parent directory exists within boundary
        parent_dir = os.path.dirname(canon_path)
        os.makedirs(parent_dir, exist_ok=True)

        try:
            with open(canon_path, "w", encoding="utf-8") as f:
                f.write(content)

            written_bytes = os.path.getsize(canon_path)
            return {
                "success": True,
                "path": canon_path,
                "relative_path": os.path.relpath(canon_path, root),
                "workspace_root": root,
                "bytes_written": written_bytes,
                "message": f"Successfully written {written_bytes} bytes to '{canon_path}'.",
            }
        except PermissionError:
            raise AuthorizationError(f"Operating system permission denied writing to '{path}'.")

    def create_directory(
        self,
        path: str,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Safely create a directory within an authorized workspace."""
        canon_path, root = self.boundary.validate_path(path, workspace_id_or_root=workspace_id)

        if os.path.exists(canon_path) and not os.path.isdir(canon_path):
            raise BadRequestError(f"A file already exists at '{path}'.")

        try:
            os.makedirs(canon_path, exist_ok=True)
            return {
                "success": True,
                "path": canon_path,
                "relative_path": os.path.relpath(canon_path, root),
                "workspace_root": root,
                "message": f"Directory '{canon_path}' is ready.",
            }
        except PermissionError:
            raise AuthorizationError(f"Operating system permission denied creating directory '{path}'.")

    def move_file(
        self,
        source_path: str,
        target_path: str,
        workspace_id: Optional[str] = None,
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        """Rename or move a file or folder between authorized paths."""
        canon_src, src_root = self.boundary.validate_path(source_path, workspace_id_or_root=workspace_id)
        canon_dst, dst_root = self.boundary.validate_path(target_path, workspace_id_or_root=workspace_id)

        if not os.path.exists(canon_src):
            raise NotFoundError(f"Source '{source_path}' does not exist.")

        if os.path.exists(canon_dst) and not overwrite:
            raise BadRequestError(f"Destination '{target_path}' already exists.")

        parent_dst = os.path.dirname(canon_dst)
        os.makedirs(parent_dst, exist_ok=True)

        try:
            shutil.move(canon_src, canon_dst)
            return {
                "success": True,
                "source": canon_src,
                "destination": canon_dst,
                "message": f"Moved '{canon_src}' to '{canon_dst}'.",
            }
        except PermissionError:
            raise AuthorizationError(f"Operating system permission denied moving '{source_path}'.")

    def delete_file(
        self,
        path: str,
        workspace_id: Optional[str] = None,
        recursive: bool = False,
        confirm: bool = False,
    ) -> Dict[str, Any]:
        """
        Delete a file or directory.
        Requires confirm=True to prevent accidental data loss.
        Never allows deleting the workspace root itself!
        """
        if not confirm:
            raise BadRequestError("Deletion rejected: 'confirm=True' must be explicitly provided.")

        canon_path, root = self.boundary.validate_path(path, workspace_id_or_root=workspace_id)

        # Protect against deleting the workspace root itself!
        if canon_path.lower() == root.lower():
            raise AuthorizationError("Access denied: cannot delete the authorized workspace root itself.")

        if not os.path.exists(canon_path):
            raise NotFoundError(f"Target '{path}' does not exist.")

        try:
            if os.path.isdir(canon_path):
                if recursive:
                    shutil.rmtree(canon_path)
                else:
                    os.rmdir(canon_path)
            else:
                os.remove(canon_path)

            return {
                "success": True,
                "path": canon_path,
                "message": f"Successfully deleted '{canon_path}'.",
            }
        except OSError as e:
            if "not empty" in str(e).lower() and not recursive:
                raise BadRequestError(f"Directory '{path}' is not empty. Pass recursive=True to delete.")
            raise

    def search_files(
        self,
        query: str,
        workspace_id: Optional[str] = None,
        search_type: str = "filename",
        max_results: int = 50,
    ) -> Dict[str, Any]:
        """
        Search files in authorized workspace by filename/glob pattern or content substring.
        search_type: 'filename' (default) or 'content'
        """
        if workspace_id:
            ws = self.workspaces.get_workspace(workspace_id)
            if not ws:
                raise NotFoundError(f"Workspace '{workspace_id}' not found.")
            roots = [ws.path]
        else:
            roots = [w.path for w in self.workspaces.list_authorized_workspaces(enabled_only=True)]

        results = []
        query_lower = query.lower()

        for r in roots:
            canon_root = self.boundary.canonicalize(r)
            if not canon_root or not os.path.exists(canon_root):
                continue

            for dirpath, dirnames, filenames in os.walk(canon_root):
                # Prune noisy directories
                dirnames[:] = [d for d in dirnames if d not in DEFAULT_EXCLUDED_DIRS and not d.startswith(".")]

                for fname in filenames:
                    if len(results) >= max_results:
                        break

                    full_path = os.path.join(dirpath, fname)
                    rel_path = os.path.relpath(full_path, canon_root)

                    if search_type == "filename":
                        if query_lower in fname.lower() or fnmatch.fnmatch(fname.lower(), query_lower):
                            results.append({
                                "name": fname,
                                "path": full_path,
                                "relative_path": rel_path,
                                "workspace_root": canon_root,
                            })
                    elif search_type == "content":
                        # Check file size before reading
                        try:
                            if os.path.getsize(full_path) < 500_000:
                                with open(full_path, "r", encoding="utf-8", errors="ignore") as fp:
                                    content = fp.read()
                                    if query_lower in content.lower():
                                        results.append({
                                            "name": fname,
                                            "path": full_path,
                                            "relative_path": rel_path,
                                            "workspace_root": canon_root,
                                        })
                        except Exception:
                            pass

                if len(results) >= max_results:
                    break
            if len(results) >= max_results:
                break

        return {
            "query": query,
            "search_type": search_type,
            "total_matches": len(results),
            "results": results,
        }

    def get_file_tree(
        self,
        path: Optional[str] = None,
        workspace_id: Optional[str] = None,
        max_depth: int = 3,
        max_entries: int = 200,
    ) -> Dict[str, Any]:
        """Generate a bounded recursive directory tree summary."""
        target = path or ""
        if not target and workspace_id:
            ws = self.workspaces.get_workspace(workspace_id)
            if ws:
                target = ws.path

        canon_path, root = self.boundary.validate_path(target, workspace_id_or_root=workspace_id)

        if not os.path.isdir(canon_path):
            raise BadRequestError(f"Path '{path}' is not a directory.")

        tree_entries = []
        count = [0]

        def _build_tree(current_path: str, depth: int) -> Dict[str, Any]:
            if depth > max_depth or count[0] >= max_entries:
                return {}

            name = os.path.basename(current_path) or current_path
            node = {
                "name": name,
                "relative_path": os.path.relpath(current_path, root),
                "is_dir": True,
                "children": [],
            }
            count[0] += 1

            try:
                items = sorted(os.listdir(current_path))
            except PermissionError:
                return node

            for item in items:
                if count[0] >= max_entries:
                    break
                if item in DEFAULT_EXCLUDED_DIRS or item.startswith("."):
                    continue

                full_item = os.path.join(current_path, item)
                if os.path.isdir(full_item):
                    if depth < max_depth:
                        child_node = _build_tree(full_item, depth + 1)
                        if child_node:
                            node["children"].append(child_node)
                    else:
                        node["children"].append({
                            "name": item,
                            "relative_path": os.path.relpath(full_item, root),
                            "is_dir": True,
                        })
                        count[0] += 1
                else:
                    node["children"].append({
                        "name": item,
                        "relative_path": os.path.relpath(full_item, root),
                        "is_dir": False,
                        "size": os.path.getsize(full_item),
                    })
                    count[0] += 1

            return node

        root_node = _build_tree(canon_path, 0)
        return {
            "root_path": canon_path,
            "workspace_root": root,
            "max_depth": max_depth,
            "total_nodes": count[0],
            "tree": root_node,
        }


fs_service = FilesystemService()
