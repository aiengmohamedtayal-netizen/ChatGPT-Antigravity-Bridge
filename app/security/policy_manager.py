import json
import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class PermissionPolicyManager:
    """
    Generates and applies permission policies for Antigravity AgentAPI,
    allowing safe headless execution without UI prompts.
    """

    DEFAULT_POLICY = {
        "version": "1.0",
        "default_action": "ask",
        "rules": [
            {
                "resource": "file_system",
                "action": "read",
                "condition": "path_in_workspace",
                "decision": "allow"
            },
            {
                "resource": "file_system",
                "action": "write",
                "condition": "path_in_workspace",
                "decision": "allow"
            },
            {
                "resource": "command_execution",
                "action": "run",
                "allowlist": [
                    "npm install", "npm run build", "npm test", "npm run dev",
                    "pytest", "python -m pytest", "python -m unittest",
                    "git status", "git diff", "git log", "git commit", "git add",
                    "tsc", "eslint", "flake8", "black"
                ],
                "decision": "allow"
            },
            {
                "resource": "command_execution",
                "action": "run",
                "denylist": [
                    "rm -rf /", "format", "del /s /q c:\\",
                    "sudo", "su"
                ],
                "decision": "deny"
            },
            {
                "resource": "mcp",
                "action": "call_tool",
                "decision": "allow"
            }
        ]
    }

    @classmethod
    def apply_policy(cls, workspace_path: str) -> bool:
        """
        Prepares the .antigravity/permissions.json in the workspace
        to enable headless operation with safe defaults.
        """
        try:
            ag_dir = os.path.join(workspace_path, ".antigravity")
            os.makedirs(ag_dir, exist_ok=True)
            
            policy_file = os.path.join(ag_dir, "permissions.json")
            
            with open(policy_file, "w", encoding="utf-8") as f:
                json.dump(cls.DEFAULT_POLICY, f, indent=2)
                
            logger.info(f"Applied headless permission policy to {policy_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to apply permission policy to {workspace_path}: {e}")
            return False

policy_manager = PermissionPolicyManager()
