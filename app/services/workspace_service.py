"""Workspace authorization service for managing multiple project roots."""

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import AuthorizationError, NotFoundError

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

    def is_restricted_path(self, path: str) -> bool:
        """Verify that path is not an entire drive root or sensitive system directory."""
        canon = self.canonicalize(path).lower()
        if not canon:
            return True

        # Check for bare drive roots like C:\ or D:\
        norm = os.path.normpath(canon)
        if norm.endswith(":") or norm.endswith(":\\") or norm == "/" or norm == "\\":
            return True

        # Check against restricted system directories
        for restricted in self.settings.RESTRICTED_SYSTEM_DIRECTORIES:
            r_canon = self.canonicalize(restricted).lower()
            if r_canon and (canon == r_canon or canon.startswith(r_canon + os.sep)):
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

    def get_workspace(self, workspace_id_or_path: str) -> Optional[AuthorizedWorkspace]:
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

        return None

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
