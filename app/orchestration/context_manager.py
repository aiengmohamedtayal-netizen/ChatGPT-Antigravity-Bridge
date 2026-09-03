"""Project Context Manager for workspace discovery, instruction aggregation, and prompt enrichment."""

import os
from pathlib import Path
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from app.models.project import Project


class ProjectContextManager:
    """Manages workspace inspection, rule ingestion, and context enrichment."""

    @staticmethod
    def inspect_workspace(workspace_path: str, max_files: int = 50) -> Dict[str, any]:
        """Scan project workspace directory and return file tree summary."""
        path = Path(workspace_path)
        if not path.exists() or not path.is_dir():
            return {
                "exists": False,
                "files_count": 0,
                "summary": [],
                "instructions": "",
            }

        files_list: List[str] = []
        instructions_content = ""
        instruction_files = ["AGENTS.md", "DESIGN.md", "README.md", "INSTRUCTIONS.md"]

        try:
            for root, dirs, files in os.walk(workspace_path):
                # Ignore noisy directories
                dirs[:] = [d for d in dirs if d not in {".git", "node_modules", ".venv", "__pycache__", "dist", "build"}]
                rel_root = os.path.relpath(root, workspace_path)

                for f in files:
                    rel_path = os.path.normpath(os.path.join(rel_root, f)) if rel_root != "." else f
                    files_list.append(rel_path)

                    if f in instruction_files and not instructions_content:
                        try:
                            with open(os.path.join(root, f), "r", encoding="utf-8", errors="ignore") as fp:
                                instructions_content = fp.read()[:4000]
                        except Exception:
                            pass

                    if len(files_list) >= max_files:
                        break
                if len(files_list) >= max_files:
                    break
        except Exception:
            pass

        return {
            "exists": True,
            "files_count": len(files_list),
            "summary": files_list[:max_files],
            "discovered_instructions": instructions_content,
        }

    @classmethod
    def assemble_normalized_prompt(
        cls,
        project: Project,
        raw_prompt: str,
        parent_task_summary: Optional[str] = None,
    ) -> str:
        """
        Combine project instructions, architectural rules, continuation lineage,
        and user instruction into a structured prompt for Antigravity.
        """
        sections = [
            f"[PROJECT CONTEXT: {project.name}]",
            f"Workspace Path: {project.workspace_path}",
        ]

        if project.instructions:
            sections.append(f"\n[ARCHITECTURAL GUIDELINES & CONVENTIONS]\n{project.instructions.strip()}")

        if parent_task_summary:
            sections.append(f"\n[PRECEDING SESSION CONTEXT]\n{parent_task_summary.strip()}")

        sections.append(f"\n[ARCHITECT INSTRUCTION / TASK]\n{raw_prompt.strip()}")

        return "\n".join(sections)


context_manager = ProjectContextManager()
