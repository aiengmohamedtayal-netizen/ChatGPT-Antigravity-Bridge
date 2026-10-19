"""Workspace authorization service for managing multiple project roots."""

import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import AuthorizationError, NotFoundError, BadRequestError

logger = logging.getLogger(__name__)


class AuthorizedWorkspace(BaseModel):
    """Model representing an authorized workspace root."""

    id: str
    name: str
    path: str
    enabled: bool = True
    description: Optional[str] = ""
    instructions: Optional[str] = ""
    exists_on_disk: bool = False


class WorkspaceService:
    """Manages dynamic multi-workspace registration, validation, and discovery."""

    def __init__(self):
        self._workspaces: Dict[str, AuthorizedWorkspace] = {}
        self.settings = get_settings()
        self.reload()

    @staticmethod
    def canonicalize(path: str) -> str:
        """Return the absolute canonical, symlink-free real path."""
        try:
            return os.path.realpath(os.path.abspath(os.path.normpath(path)))
        except Exception:
            return ""

    def is_system_directory(self, path: str) -> bool:
        """Check if path is inside a sensitive system directory (e.g. C:\\Windows, C:\\Program Files, /etc)."""
        canon = self.canonicalize(path).lower()
        if not canon:
            return True

        for restricted in self.settings.RESTRICTED_SYSTEM_DIRECTORIES:
            r_canon = self.canonicalize(restricted).lower()
            if r_canon and (canon == r_canon or canon.startswith(r_canon + os.sep)):
                return True

        if os.name == "nt":
            win_dirs = [
                os.environ.get("SystemRoot"),
                os.environ.get("ProgramFiles"),
                os.environ.get("ProgramFiles(x86)"),
                os.environ.get("ProgramData"),
            ]
            for w_dir in win_dirs:
                if w_dir:
                    w_canon = self.canonicalize(w_dir).lower()
                    if w_canon and (canon == w_canon or canon.startswith(w_canon + os.sep)):
                        return True

        return False

    def is_restricted_path(self, path: str) -> bool:
        """Verify that path is not an entire drive root or sensitive system directory."""
        if self.is_system_directory(path):
            return True

        # Check for bare drive roots like C:\ or D:\ unless ALLOW_DRIVE_ROOTS is enabled
        if not getattr(self.settings, "ALLOW_DRIVE_ROOTS", False):
            canon = self.canonicalize(path).lower()
            norm = os.path.normpath(canon)
            if norm.endswith(":") or norm.endswith(":\\") or norm == "/" or norm == "\\":
                return True

        return False

    def reload(self) -> None:
        """Reload authorized workspaces from config file and environment."""
        self._workspaces.clear()

        # 1. Load from workspaces.json config file
        config_file = self.settings.WORKSPACES_CONFIG_FILE
        if not os.path.isabs(config_file):
            config_file = os.path.join(os.getcwd(), config_file)

        if os.path.exists(config_file):
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data.get("authorized_workspaces", []):
                    ws_id = item.get("id") or f"proj_{len(self._workspaces) + 1}"
                    ws_path = item.get("path", "")
                    canon = self.canonicalize(ws_path)
                    exists = bool(canon and os.path.isdir(canon))

                    if not self.is_restricted_path(canon):
                        self._workspaces[ws_id] = AuthorizedWorkspace(
                            id=ws_id,
                            name=item.get("name", os.path.basename(canon) or ws_id),
                            path=canon if canon else ws_path,
                            enabled=item.get("enabled", True),
                            description=item.get("description", ""),
                            instructions=item.get("instructions", ""),
                            exists_on_disk=exists,
                        )
                    else:
                        logger.warning("Workspace root '%s' rejected: path is restricted.", ws_path)
            except Exception as e:
                logger.error("Error reading workspaces config '%s': %s", config_file, e)

        # 2. Load from AUTHORIZED_WORKSPACES environment variable if configured
        env_workspaces = self.settings.AUTHORIZED_WORKSPACES
        if env_workspaces:
            if env_workspaces.strip().startswith("[") or env_workspaces.strip().startswith("{"):
                try:
                    parsed = json.loads(env_workspaces)
                    items = parsed if isinstance(parsed, list) else parsed.get("authorized_workspaces", [])
                    for item in items:
                        p = item if isinstance(item, str) else item.get("path", "")
                        canon = self.canonicalize(p)
                        if canon and not self.is_restricted_path(canon):
                            ws_id = item.get("id", f"proj_env_{len(self._workspaces) + 1}") if isinstance(item, dict) else f"proj_env_{len(self._workspaces) + 1}"
                            self._workspaces[ws_id] = AuthorizedWorkspace(
                                id=ws_id,
                                name=item.get("name", os.path.basename(canon)) if isinstance(item, dict) else os.path.basename(canon),
                                path=canon,
                                enabled=True,
                                exists_on_disk=os.path.isdir(canon),
                            )
                except Exception as e:
                    logger.error("Failed to parse AUTHORIZED_WORKSPACES JSON: %s", e)
            else:
                for idx, raw_path in enumerate(env_workspaces.split(",")):
                    clean = raw_path.strip()
                    if clean:
                        canon = self.canonicalize(clean)
                        if canon and not self.is_restricted_path(canon):
                            ws_id = f"proj_env_{idx + 1}"
                            self._workspaces[ws_id] = AuthorizedWorkspace(
                                id=ws_id,
                                name=os.path.basename(canon) or ws_id,
                                path=canon,
                                enabled=True,
                                exists_on_disk=os.path.isdir(canon),
                            )

        # 3. Fallback: ensure current working directory is authorized if no roots defined
        if not self._workspaces:
            cwd_canon = self.canonicalize(os.getcwd())
            self._workspaces["proj_default"] = AuthorizedWorkspace(
                id="proj_default",
                name="Default Workspace",
                path=cwd_canon,
                enabled=True,
                exists_on_disk=True,
            )

        logger.info("Loaded %d authorized workspaces.", len(self._workspaces))

    def list_authorized_workspaces(self, enabled_only: bool = True) -> List[AuthorizedWorkspace]:
        """Return all registered authorized workspaces."""
        workspaces = list(self._workspaces.values())
        if enabled_only:
            workspaces = [w for w in workspaces if w.enabled]
        for w in workspaces:
            w.exists_on_disk = bool(w.path and os.path.isdir(w.path))
        return workspaces

    def get_workspace(self, workspace_id_or_path: str, auto_provision: bool = True) -> Optional[AuthorizedWorkspace]:
        """Resolve an authorized workspace by its ID or canonical path or name."""
        if not workspace_id_or_path:
            return None

        # Direct ID lookup
        if workspace_id_or_path in self._workspaces:
            ws = self._workspaces[workspace_id_or_path]
            ws.exists_on_disk = bool(ws.path and os.path.isdir(ws.path))
            return ws

        # Canonical path lookup
        target_canon = self.canonicalize(workspace_id_or_path).lower()
        for ws in self._workspaces.values():
            if self.canonicalize(ws.path).lower() == target_canon:
                ws.exists_on_disk = bool(ws.path and os.path.isdir(ws.path))
                return ws

        # Case-insensitive name lookup
        for ws in self._workspaces.values():
            if ws.name.lower() == workspace_id_or_path.lower():
                ws.exists_on_disk = bool(ws.path and os.path.isdir(ws.path))
                return ws

        # Fallback: check database Project table
        try:
            from app import database
            from app.models.project import Project
            local_db = database.SessionLocal()
            try:
                proj = local_db.query(Project).filter(
                    (Project.id == workspace_id_or_path) |
                    (Project.workspace_path == workspace_id_or_path)
                ).first()
                if proj and not self.is_restricted_path(proj.workspace_path):
                    canon = self.canonicalize(proj.workspace_path)
                    ws = AuthorizedWorkspace(
                        id=proj.id,
                        name=proj.name,
                        path=canon,
                        enabled=True,
                        description=proj.description or "",
                        instructions=proj.instructions or "",
                        exists_on_disk=bool(canon and os.path.isdir(canon)),
                    )
                    return ws
            finally:
                local_db.close()
        except Exception:
            pass

        # Smart Resolution: "training/test" -> find "training", append "test", auto-register
        parts = workspace_id_or_path.replace("\\", "/").strip("/").split("/")
        if len(parts) > 1:
            base_name = parts[0]
            sub_path = os.path.join(*parts[1:])
            # Don't recurse infinitely, just check existing workspaces
            base_ws = self._workspaces.get(base_name)
            if not base_ws:
                for ws in self._workspaces.values():
                    if ws.name.lower() == base_name.lower():
                        base_ws = ws
                        break
            
            if base_ws:
                target_path = os.path.join(base_ws.path, sub_path)
                canon_target = self.canonicalize(target_path)
                if canon_target and not self.is_restricted_path(canon_target):
                    try:
                        if os.path.commonpath([canon_target, base_ws.path]).lower() == base_ws.path.lower():
                            if not os.path.exists(canon_target):
                                os.makedirs(canon_target, exist_ok=True)
                            new_id = f"{base_ws.id}_{sub_path.replace(os.sep, '_').replace('/', '_')}"
                            return self.register_workspace(
                                path=canon_target,
                                name=f"{base_ws.name} ({sub_path})",
                                workspace_id=new_id,
                                description=f"Auto-resolved sub-workspace of {base_ws.name}",
                                save_to_config=True
                            )
                    except ValueError:
                        pass

        # Auto-Discovery Fallback
        from app.services.discovery_service import discovery_service
        discovered = discovery_service.discover_all(max_depth=2)
        target_lower = workspace_id_or_path.lower()
        for d in discovered:
            if d.id.lower() == target_lower or d.name.lower() == target_lower:
                return self.register_workspace(
                    path=d.path,
                    name=d.name,
                    workspace_id=d.id,
                    description=f"Auto-discovered {d.framework} project",
                    save_to_config=True
                )

        # Autonomous Provisioning Fallback (if requested path falls inside an authorized root)
        if auto_provision:
            provisioned = self.auto_provision_workspace(workspace_id_or_path)
            if provisioned:
                return provisioned

        return None

    def auto_provision_workspace(
        self,
        path_or_subpath: str,
        name: Optional[str] = None,
        description: str = "",
        instructions: str = "",
        auto_create_dir: bool = True,
    ) -> Optional[AuthorizedWorkspace]:
        """Autonomously provision a workspace if the target path falls inside an authorized root.
        Creates directory on the fly (mkdir -p), registers in workspaces.json, and returns the workspace.
        """
        if not path_or_subpath or not isinstance(path_or_subpath, str):
            return None

        # Traversal check
        if ".." in path_or_subpath.replace("\\", "/").split("/"):
            return None

        clean = path_or_subpath.strip()

        # Only auto-provision if target looks like a path (is absolute, or has path separators, or drive prefix)
        is_path_expression = os.path.isabs(clean) or ("/" in clean) or ("\\" in clean) or (len(clean) >= 2 and clean[1] == ":")
        if not is_path_expression:
            return None

        # Candidate canonical paths
        candidate_paths: List[str] = []
        if os.path.isabs(clean) or (len(clean) >= 2 and clean[1] == ":"):
            c = self.canonicalize(clean)
            if c:
                candidate_paths.append(c)
        else:
            # Check relative to all enabled authorized workspace roots
            for ws in self.list_authorized_workspaces(enabled_only=True):
                c = self.canonicalize(os.path.join(ws.path, clean.lstrip("/\\")))
                if c and c not in candidate_paths:
                    candidate_paths.append(c)

        for canon_path in candidate_paths:
            if not canon_path:
                continue

            # Check restricted system directory (e.g. C:\\Windows, C:\\Program Files)
            if self.is_restricted_path(canon_path):
                continue

            # Must fall strictly within an authorized root
            is_auth, matching_ws, _ = self.match_path_to_workspace(canon_path)
            if not is_auth or not matching_ws:
                continue

            # If it's the root itself, return the matching root
            if canon_path.lower() == self.canonicalize(matching_ws.path).lower():
                return matching_ws

            # Check if already registered
            for ws in self._workspaces.values():
                if self.canonicalize(ws.path).lower() == canon_path.lower():
                    return ws

            # Ensure directory exists on disk (mkdir -p semantics)
            if auto_create_dir:
                try:
                    os.makedirs(canon_path, exist_ok=True)
                except Exception as e:
                    logger.error("Failed to auto-create directory '%s': %s", canon_path, e)
                    continue

            base_name = os.path.basename(canon_path).replace(" ", "_").lower()
            if not base_name:
                base_name = "workspace"
            ws_id = f"proj_{base_name}"
            if ws_id in self._workspaces:
                ws_id = f"proj_{base_name}_{len(self._workspaces) + 1}"

            ws_name = name or os.path.basename(canon_path) or ws_id
            desc = description or f"Auto-provisioned workspace under {matching_ws.name}"

            logger.info("Auto-provisioned workspace: id='%s', name='%s', path='%s'", ws_id, ws_name, canon_path)

            return self.register_workspace(
                path=canon_path,
                name=ws_name,
                workspace_id=ws_id,
                description=desc,
                instructions=instructions,
                enabled=True,
                save_to_config=True,
            )

        return None

    def init_project_workspace(
        self,
        path: str,
        name: Optional[str] = None,
        description: str = "",
        instructions: str = "",
        scaffold: str = "git",
        init_git: bool = True,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """Dedicated tool logic: Autonomously create a project directory, initialize scaffolds,
        and register it as an active workspace in one call.
        """
        if not path or not isinstance(path, str):
            raise BadRequestError("Path must be a non-empty string.")

        if ".." in path.replace("\\", "/").split("/"):
            raise AuthorizationError("Path traversal ('..') is strictly prohibited.")

        clean = path.strip()
        if os.path.isabs(clean) or (len(clean) >= 2 and clean[1] == ":"):
            canon_path = self.canonicalize(clean)
        else:
            roots = self.list_authorized_workspaces(enabled_only=True)
            if not roots:
                raise NotFoundError("No authorized workspace roots available.")
            canon_path = self.canonicalize(os.path.join(roots[0].path, clean.lstrip("/\\")))

        if not canon_path:
            raise BadRequestError(f"Invalid path: '{path}'.")

        # Security check 1: Restricted system directory
        if self.is_restricted_path(canon_path):
            raise AuthorizationError(f"Access denied: '{path}' is inside a restricted system directory.")

        # Security check 2: Must fall within an authorized root
        is_auth, matching_ws, _ = self.match_path_to_workspace(canon_path)
        if not is_auth or not matching_ws:
            raise AuthorizationError(f"Access denied: '{path}' is outside the authorized workspace roots.")

        # 1. Create directory on disk (mkdir -p)
        try:
            os.makedirs(canon_path, exist_ok=True)
        except PermissionError:
            raise AuthorizationError(f"OS permission denied creating directory '{canon_path}'.")

        created_files: List[str] = []

        # 2. Git Initialization
        git_status = "disabled"
        if init_git:
            try:
                git_dir = os.path.join(canon_path, ".git")
                if not os.path.exists(git_dir):
                    if shutil.which("git"):
                        run_res = subprocess.run(
                            ["git", "init"],
                            cwd=canon_path,
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )
                        if run_res.returncode == 0:
                            git_status = "initialized"
                            created_files.append(".git/")
                        else:
                            git_status = f"git init failed: {run_res.stderr.strip()}"
                    else:
                        git_status = "git binary not found on PATH"
                else:
                    git_status = "already a git repository"
            except Exception as e:
                git_status = f"git init error: {str(e)}"

        # 3. Scaffolding Templates
        project_name = name or os.path.basename(canon_path) or "New Project"
        scaffold_type = (scaffold or "git").lower()

        # .gitignore
        if scaffold_type in ("git", "python", "node", "web"):
            gitignore_path = os.path.join(canon_path, ".gitignore")
            if not os.path.exists(gitignore_path):
                gitignore_content = (
                    "# Environments & Dependencies\n"
                    ".env\n"
                    ".env.local\n"
                    "node_modules/\n"
                    "__pycache__/\n"
                    "*.py[cod]\n"
                    "*.pyo\n"
                    ".venv/\n"
                    "env/\n"
                    "dist/\n"
                    "build/\n"
                    ".DS_Store\n"
                    "Thumbs.db\n"
                )
                with open(gitignore_path, "w", encoding="utf-8") as f:
                    f.write(gitignore_content)
                created_files.append(".gitignore")

        # README.md
        readme_path = os.path.join(canon_path, "README.md")
        if not os.path.exists(readme_path):
            readme_content = (
                f"# {project_name}\n\n"
                f"{description or 'Project workspace initialized via ChatGPT x Antigravity Bridge.'}\n\n"
                "## Overview\n"
                "This project is managed autonomously with ChatGPT and Google Antigravity.\n"
            )
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write(readme_content)
            created_files.append("README.md")

        # AGENTS.md (if instructions provided)
        if instructions:
            agents_md_path = os.path.join(canon_path, "AGENTS.md")
            if not os.path.exists(agents_md_path):
                with open(agents_md_path, "w", encoding="utf-8") as f:
                    f.write(f"# Agent Guidelines for {project_name}\n\n{instructions}\n")
                created_files.append("AGENTS.md")

        # Scaffold specific files
        if scaffold_type == "python":
            pyproject_path = os.path.join(canon_path, "pyproject.toml")
            if not os.path.exists(pyproject_path):
                pkg_name = project_name.replace("-", "_").replace(" ", "_").lower()
                pyproject_content = (
                    "[project]\n"
                    f'name = "{pkg_name}"\n'
                    'version = "0.1.0"\n'
                    f'description = "{description or project_name}"\n'
                    'readme = "README.md"\n'
                    'requires-python = ">=3.10"\n'
                    "dependencies = []\n"
                )
                with open(pyproject_path, "w", encoding="utf-8") as f:
                    f.write(pyproject_content)
                created_files.append("pyproject.toml")

            main_py_path = os.path.join(canon_path, "main.py")
            if not os.path.exists(main_py_path):
                with open(main_py_path, "w", encoding="utf-8") as f:
                    f.write(f'def main():\n    print("Hello from {project_name}!")\n\nif __name__ == "__main__":\n    main()\n')
                created_files.append("main.py")

        elif scaffold_type == "node":
            pkg_json_path = os.path.join(canon_path, "package.json")
            if not os.path.exists(pkg_json_path):
                pkg_name = project_name.replace(" ", "-").lower()
                pkg_content = json.dumps({
                    "name": pkg_name,
                    "version": "1.0.0",
                    "description": description or project_name,
                    "main": "src/index.js",
                    "scripts": {
                        "start": "node src/index.js"
                    },
                    "private": True,
                }, indent=2)
                with open(pkg_json_path, "w", encoding="utf-8") as f:
                    f.write(pkg_content)
                created_files.append("package.json")

            src_dir = os.path.join(canon_path, "src")
            os.makedirs(src_dir, exist_ok=True)
            index_js_path = os.path.join(src_dir, "index.js")
            if not os.path.exists(index_js_path):
                with open(index_js_path, "w", encoding="utf-8") as f:
                    f.write(f'console.log("Hello from {project_name}!");\n')
                created_files.append("src/index.js")

        elif scaffold_type == "web":
            html_path = os.path.join(canon_path, "index.html")
            if not os.path.exists(html_path):
                html_content = (
                    "<!DOCTYPE html>\n"
                    '<html lang="en">\n<head>\n'
                    '  <meta charset="UTF-8">\n'
                    f"  <title>{project_name}</title>\n"
                    '  <link rel="stylesheet" href="style.css">\n'
                    "</head>\n<body>\n"
                    f"  <h1>Welcome to {project_name}</h1>\n"
                    '  <script src="app.js"></script>\n'
                    "</body>\n</html>\n"
                )
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                created_files.append("index.html")

            css_path = os.path.join(canon_path, "style.css")
            if not os.path.exists(css_path):
                with open(css_path, "w", encoding="utf-8") as f:
                    f.write("body {\n  font-family: system-ui, sans-serif;\n  margin: 2rem;\n}\n")
                created_files.append("style.css")

            js_path = os.path.join(canon_path, "app.js")
            if not os.path.exists(js_path):
                with open(js_path, "w", encoding="utf-8") as f:
                    f.write(f'console.log("{project_name} web app loaded.");\n')
                created_files.append("app.js")

        # 4. Register workspace
        base_id = os.path.basename(canon_path).replace(" ", "_").lower()
        ws_id = f"proj_{base_id}"
        if ws_id in self._workspaces:
            if self.canonicalize(self._workspaces[ws_id].path).lower() != canon_path.lower():
                ws_id = f"proj_{base_id}_{len(self._workspaces) + 1}"

        ws = self.register_workspace(
            path=canon_path,
            name=project_name,
            workspace_id=ws_id,
            description=description or f"Project workspace initialized under {matching_ws.name}",
            instructions=instructions,
            enabled=True,
            save_to_config=True,
        )

        # 5. Sync with database
        if db is not None:
            self.sync_with_db(db)

        return {
            "success": True,
            "workspace_id": ws.id,
            "name": ws.name,
            "path": ws.path,
            "root_workspace": matching_ws.name,
            "scaffold": scaffold_type,
            "git_status": git_status,
            "created_files": created_files,
            "status": "ready",
            "message": f"Workspace '{ws.name}' ({ws.id}) successfully initialized and ready for Antigravity Agent sessions.",
        }

    def discover_and_register_all(self) -> List[AuthorizedWorkspace]:
        """Runs discovery and automatically registers all safe projects found."""
        from app.services.discovery_service import discovery_service
        discovered = discovery_service.discover_all(max_depth=2)
        added = []
        for d in discovered:
            if d.id not in self._workspaces and not self.is_restricted_path(d.path):
                # Check if it's already registered under another ID
                if not any(self.canonicalize(w.path).lower() == self.canonicalize(d.path).lower() for w in self._workspaces.values()):
                    ws = self.register_workspace(
                        path=d.path,
                        name=d.name,
                        workspace_id=d.id,
                        description=f"Auto-discovered {d.framework} project",
                        save_to_config=True
                    )
                    added.append(ws)
        return added

    def match_path_to_workspace(self, target_path: str) -> Tuple[bool, Optional[AuthorizedWorkspace], str]:
        """
        Verify if a target_path falls within ANY authorized workspace root.
        Returns (is_authorized, matching_workspace, canonical_target_path).
        """
        canon_target = self.canonicalize(target_path)
        if not canon_target:
            return False, None, ""

        for ws in self._workspaces.values():
            if not ws.enabled:
                continue
            canon_root = self.canonicalize(ws.path)
            if not canon_root or not os.path.exists(canon_root):
                continue

            try:
                common = os.path.commonpath([canon_target, canon_root])
                if common.lower() == canon_root.lower():
                    return True, ws, canon_target
            except ValueError:
                continue

        return False, None, canon_target

    def register_workspace(
        self,
        path: str,
        name: Optional[str] = None,
        workspace_id: Optional[str] = None,
        description: str = "",
        instructions: str = "",
        enabled: bool = True,
        save_to_config: bool = True,
    ) -> AuthorizedWorkspace:
        """Authorize and register a new workspace root."""
        canon = self.canonicalize(path)
        if not canon or not os.path.isdir(canon):
            raise NotFoundError(f"Workspace root '{path}' does not exist on disk.")

        if self.is_restricted_path(canon):
            raise AuthorizationError(f"Path '{path}' is a restricted system directory or drive root.")

        ws_id = workspace_id or f"proj_{os.path.basename(canon).replace(' ', '_').lower()}_{len(self._workspaces) + 1}"
        ws_name = name or os.path.basename(canon) or ws_id

        ws = AuthorizedWorkspace(
            id=ws_id,
            name=ws_name,
            path=canon,
            enabled=enabled,
            description=description,
            instructions=instructions,
            exists_on_disk=True,
        )
        self._workspaces[ws_id] = ws

        if save_to_config:
            self._save_to_config_file()

        return ws

    def _save_to_config_file(self) -> None:
        """Persist authorized workspaces to workspaces.json."""
        config_file = self.settings.WORKSPACES_CONFIG_FILE
        if not os.path.isabs(config_file):
            config_file = os.path.join(os.getcwd(), config_file)

        data = {
            "authorized_workspaces": [
                {
                    "id": w.id,
                    "name": w.name,
                    "path": w.path,
                    "enabled": w.enabled,
                    "description": w.description,
                    "instructions": w.instructions,
                }
                for w in self._workspaces.values()
            ]
        }
        try:
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("Failed to persist workspaces to '%s': %s", config_file, e)

    def sync_with_db(self, db: Session) -> None:
        """Synchronize authorized workspaces with the SQLite Project records."""
        from app.models.project import Project

        for ws in self.list_authorized_workspaces(enabled_only=False):
            proj = db.query(Project).filter(Project.id == ws.id).first()
            if not proj:
                proj = db.query(Project).filter(Project.workspace_path == ws.path).first()

            if not proj:
                new_proj = Project(
                    id=ws.id,
                    name=ws.name,
                    workspace_path=ws.path,
                    description=ws.description or "",
                    instructions=ws.instructions or "",
                )
                db.add(new_proj)
            else:
                proj.name = ws.name
                proj.workspace_path = ws.path
                if ws.description:
                    proj.description = ws.description
                if ws.instructions:
                    proj.instructions = ws.instructions
        db.commit()


workspace_service = WorkspaceService()
