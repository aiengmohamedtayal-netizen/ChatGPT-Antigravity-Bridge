import os
import json
import time
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from app.config import get_settings

logger = logging.getLogger(__name__)

@dataclass
class DiscoveredProject:
    id: str
    name: str
    path: str
    framework: str
    language: str
    package_manager: str
    detected: bool
    detection_reason: str
    confidence: int

class WorkspaceDiscoveryService:
    def __init__(self):
        self.settings = get_settings()
        self.discovery_roots = self._parse_discovery_roots()

    def _parse_discovery_roots(self) -> List[str]:
        roots_str = getattr(self.settings, "WORKSPACE_DISCOVERY_ROOTS", "")
        if not roots_str:
            # Defaults if none provided
            home = os.path.expanduser("~")
            roots = [
                os.path.join(home, "Projects"),
                os.path.join(home, "Documents"),
                "D:\\PROJECTS"
            ]
        else:
            roots = [r.strip() for r in roots_str.split(",")]
        
        return [os.path.normpath(r) for r in roots if os.path.exists(r) and os.path.isdir(r)]

    def _analyze_project(self, path: str) -> Dict[str, Any]:
        """Analyze a directory to determine framework, language, and package manager."""
        files = set()
        try:
            for entry in os.scandir(path):
                if entry.is_file():
                    files.add(entry.name.lower())
        except Exception:
            return {"detected": False, "reason": "access_denied", "confidence": 0}

        if not files:
            return {"detected": False, "reason": "empty_dir", "confidence": 0}

        framework = "unknown"
        language = "unknown"
        pkg_mgr = "unknown"
        confidence = 0
        reasons = []

        if "package.json" in files:
            pkg_mgr = "npm"
            confidence += 30
            reasons.append("package.json")
            language = "javascript"
            
            if "tsconfig.json" in files:
                language = "typescript"
                confidence += 20
                reasons.append("tsconfig.json")
                
            if "next.config.js" in files or "next.config.mjs" in files or "next.config.ts" in files:
                framework = "nextjs"
                confidence += 30
                reasons.append("next.config")
            elif "vite.config.js" in files or "vite.config.ts" in files:
                framework = "vite"
                confidence += 30
                reasons.append("vite.config")

        if "pyproject.toml" in files or "requirements.txt" in files or "setup.py" in files:
            language = "python"
            pkg_mgr = "pip"
            confidence += 40
            reasons.append("python_files")
            
        if "cargo.toml" in files:
            language = "rust"
            pkg_mgr = "cargo"
            confidence += 50
            reasons.append("cargo.toml")
            
        if "pom.xml" in files:
            language = "java"
            pkg_mgr = "maven"
            confidence += 50
            reasons.append("pom.xml")

        if "build.gradle" in files:
            language = "java"
            pkg_mgr = "gradle"
            confidence += 50
            reasons.append("build.gradle")

        if ".git" in set(f.name.lower() for f in os.scandir(path) if f.is_dir()):
            confidence += 20
            reasons.append(".git")

        return {
            "detected": confidence > 0,
            "framework": framework,
            "language": language,
            "package_manager": pkg_mgr,
            "reason": ", ".join(reasons) if reasons else "no_markers",
            "confidence": confidence
        }

    def discover_all(self, max_depth: int = 2) -> List[DiscoveredProject]:
        """Scans discovery roots up to max_depth."""
        results = []
        for root in self.discovery_roots:
            results.extend(self._scan_directory(root, current_depth=0, max_depth=max_depth))
        return results

    def _scan_directory(self, path: str, current_depth: int, max_depth: int) -> List[DiscoveredProject]:
        results = []
        if current_depth > max_depth:
            return results
            
        try:
            for entry in os.scandir(path):
                if entry.is_dir():
                    # Skip hidden/system directories
                    if entry.name.startswith(".") or entry.name in ("node_modules", "venv", "__pycache__"):
                        continue
                        
                    proj_path = entry.path
                    analysis = self._analyze_project(proj_path)
                    
                    if analysis["detected"]:
                        pid = f"proj_{entry.name.lower().replace(' ', '_')}"
                        results.append(DiscoveredProject(
                            id=pid,
                            name=entry.name,
                            path=proj_path,
                            framework=analysis["framework"],
                            language=analysis["language"],
                            package_manager=analysis["package_manager"],
                            detected=True,
                            detection_reason=analysis["reason"],
                            confidence=analysis["confidence"]
                        ))
                    else:
                        # Go deeper if not a project itself
                        results.extend(self._scan_directory(proj_path, current_depth + 1, max_depth))
        except Exception as e:
            logger.warning(f"Error scanning {path}: {e}")
            
        return results

discovery_service = WorkspaceDiscoveryService()
