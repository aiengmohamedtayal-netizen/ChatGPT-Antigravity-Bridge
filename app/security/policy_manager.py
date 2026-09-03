import json
import os
import uuid
import urllib.parse
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class PermissionPolicyManager:
    """
    Generates and applies permission policies for Antigravity AgentAPI,
    allowing safe headless execution without UI prompts by natively manipulating
    the ~/.gemini/config/projects/ settings files.
    """

    @classmethod
    def get_projects_dir(cls) -> str:
        # Resolve Antigravity config directory (e.g. C:\\Users\\Name\\.gemini\\config\\projects)
        # We can get the home directory via os.path.expanduser("~")
        gemini_dir = os.path.join(os.path.expanduser("~"), ".gemini")
        return os.path.join(gemini_dir, "config", "projects")

    @classmethod
    def _normalize_uri_to_path(cls, uri: str) -> str:
        if not uri:
            return ""
        if uri.startswith("file:///"):
            uri = uri[8:]
        # Decode URL encoding (e.g., d%3A -> d:)
        decoded = urllib.parse.unquote(uri)
        # Normalize slashes
        return os.path.normpath(decoded.replace("/", os.sep))

    @classmethod
    def _path_to_uri(cls, path: str) -> str:
        # e.g. d:\PROJECTS\tool -> file:///d%3A/PROJECTS/tool
        # Antigravity typically uses uppercase drive letter or lowercase, we'll format as d%3A/
        path = os.path.abspath(path).replace(os.sep, "/")
        if len(path) > 1 and path[1] == ":":
            drive = path[0].lower()
            rest = path[2:]
            path = f"{drive}:{rest}"
        encoded = urllib.parse.quote(path, safe="/")
        return f"file:///{encoded.replace(':', '%3A')}"

    @classmethod
    def apply_policy(cls, workspace_path: str) -> bool:
        """
        Ensures a project config exists in ~/.gemini/config/projects/ for this workspace,
        and injects the necessary Headless Execution Policies (autoExecutionPolicy ON, etc).
        """
        try:
            projects_dir = cls.get_projects_dir()
            os.makedirs(projects_dir, exist_ok=True)
            
            target_path = os.path.normpath(os.path.abspath(workspace_path)).lower()
            
            project_file = None
            project_data = {}
            
            # 1. Search for existing project
            for f in os.listdir(projects_dir):
                if not f.endswith(".json"):
                    continue
                file_path = os.path.join(projects_dir, f)
                try:
                    with open(file_path, "r", encoding="utf-8") as f_in:
                        data = json.load(f_in)
                        resources = data.get("projectResources", {}).get("resources", [])
                        for res in resources:
                            uri = res.get("folderUri", "")
                            if cls._normalize_uri_to_path(uri).lower() == target_path:
                                project_file = file_path
                                project_data = data
                                break
                    if project_file:
                        break
                except Exception:
                    pass
                    
            # 2. If not found, create a new one
            if not project_file:
                project_id = str(uuid.uuid4())
                project_file = os.path.join(projects_dir, f"{project_id}.json")
                project_data = {
                    "id": project_id,
                    "name": os.path.basename(workspace_path),
                    "projectResources": {
                        "resources": [
                            {"folderUri": cls._path_to_uri(workspace_path)}
                        ]
                    }
                }
                
            # 3. Inject Headless Permissions and Auto-Execution Policy
            if "settings" not in project_data:
                project_data["settings"] = {}
                
            project_data["settings"]["fileAccessPolicy"] = "AGENT_SETTING_POLICY_ALLOW"
            project_data["settings"]["autoExecutionPolicy"] = "CASCADE_COMMANDS_AUTO_EXECUTION_ON"
            project_data["settings"]["artifactReviewMode"] = "ARTIFACT_REVIEW_MODE_TURBO"
            
            # Grant global run permissions for safe commands (or just wildcard for headless autonomous)
            if "permissionGrants" not in project_data:
                project_data["permissionGrants"] = {}
            if "permissionGrants" not in project_data["permissionGrants"]:
                project_data["permissionGrants"]["permissionGrants"] = {}
                
            allow_list = project_data["permissionGrants"]["permissionGrants"].get("allow", [])
            # In a real production system, this could be restricted. But for the Bridge's AgentAPI headless operation,
            # we need to authorize commands so the GUI doesn't block. 
            # (Note: we still rely on Bridge's orchestrator to block dangerous paths).
            headless_commands = [
                "command(npm)", "command(pytest)", "command(python)", "command(git)", 
                "command(npx)", "command(pnpm)", "command(node)", "command(tsc)"
            ]
            for cmd in headless_commands:
                if cmd not in allow_list:
                    allow_list.append(cmd)
            project_data["permissionGrants"]["permissionGrants"]["allow"] = allow_list
            
            # 4. Save
            with open(project_file, "w", encoding="utf-8") as f_out:
                json.dump(project_data, f_out, indent=2)
                
            logger.info(f"Applied native Antigravity Headless permissions to {project_file}")
            
            # Also, write to .antigravity/permissions.json just for legacy/diagnostic tracking
            ag_dir = os.path.join(workspace_path, ".antigravity")
            os.makedirs(ag_dir, exist_ok=True)
            with open(os.path.join(ag_dir, "permissions.json"), "w", encoding="utf-8") as f_out:
                json.dump({"headless_policy_applied_via": project_file}, f_out, indent=2)
                
            return True
        except Exception as e:
            logger.error(f"Failed to apply native Antigravity permission policy to {workspace_path}: {e}")
            return False

policy_manager = PermissionPolicyManager()
