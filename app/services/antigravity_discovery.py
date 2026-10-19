"""
Antigravity Language Server Dynamic Discovery Service.

Autonomously detects, probes, and injects runtime connection credentials
(ANTIGRAVITY_LS_ADDRESS, ANTIGRAVITY_CSRF_TOKEN, ANTIGRAVITY_APP_DATA_DIR)
for the Antigravity Language Server on Windows and POSIX systems.
Eliminates manual environment variable exports and handles dynamic IDE restarts.
"""

import asyncio
import json
import logging
import os
import re
import subprocess
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("antigravity.discovery")


class AntigravityDiscoveryService:
    """
    Manages autonomous discovery and caching of Antigravity Language Server
    gRPC/HTTP endpoint address and CSRF authorization tokens.
    """

    def __init__(self) -> None:
        self._cached_address: Optional[str] = None
        self._cached_token: Optional[str] = None
        self._cached_at: float = 0.0
        self._cache_ttl_seconds: float = 60.0  # Re-verify every 60 seconds

    def invalidate_cache(self) -> None:
        """Invalidate currently cached address and CSRF token."""
        self._cached_address = None
        self._cached_token = None
        self._cached_at = 0.0
        logger.info("Invalidated Antigravity Language Server credential cache.")

    def verify_credentials(self, cli_path: str, address: str, csrf_token: Optional[str] = None) -> bool:
        """
        Actively probes the candidate address and token against agentapi.
        Returns True if the server responds with valid gRPC frames (even trajectory not found).
        Returns False if connection is refused, server preface fails, or authentication is rejected.
        """
        if not os.path.exists(cli_path):
            return False

        env = os.environ.copy()
        env["ANTIGRAVITY_LS_ADDRESS"] = address
        if csrf_token:
            env["ANTIGRAVITY_CSRF_TOKEN"] = csrf_token

        try:
            proc = subprocess.run(
                [cli_path, "get-conversation-metadata", "__bridge_health_probe__"],
                env=env,
                capture_output=True,
                text=True,
                timeout=3,
            )
            combined = (proc.stdout + " " + proc.stderr).lower()

            # Fatal connection/auth failure indicators
            if any(term in combined for term in [
                "connection error",
                "connection refused",
                "missing csrf token",
                "unauthenticated",
                "error reading server preface",
                "forcibly closed",
            ]):
                return False

            # Positive indicators that gRPC endpoint accepted connection and authenticated
            if "trajectory not found" in combined or "not found" in combined or proc.returncode == 0:
                return True

            # If returncode is 0 without error, it succeeded
            return proc.returncode == 0
        except Exception as exc:
            logger.debug("Probe failed for address %s: %s", address, exc)
            return False

    def _discover_from_process(self) -> Optional[Dict[str, object]]:
        """
        Inspects running processes to locate language_server.exe and extract
        active listening ports and command-line arguments (including --csrf_token).
        """
        if os.name != "nt":
            # POSIX fallback using pgrep / lsof if needed
            return None

        ps_script = """
        $p = Get-CimInstance Win32_Process -Filter "name='language_server.exe'" | Select-Object -First 1 ProcessId, CommandLine
        if ($p) {
            $ports = Get-NetTCPConnection -OwningProcess $p.ProcessId -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty LocalPort
            [PSCustomObject]@{
                pid = $p.ProcessId
                cmd = $p.CommandLine
                ports = @($ports)
            } | ConvertTo-Json -Compress
        }
        """
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=8,
            )
            if res.returncode != 0 or not res.stdout.strip():
                return None

            data = json.loads(res.stdout.strip())
            cmd = data.get("cmd", "")
            raw_ports = data.get("ports", [])
            ports = [raw_ports] if isinstance(raw_ports, int) else list(raw_ports)

            csrf_match = re.search(r"--csrf_token[=\s]+([^\s]+)", cmd)
            csrf_token = csrf_match.group(1) if csrf_match else None

            hb_match = re.search(r"--host_bridge_url[=\s]+http://127\.0\.0\.1:(\d+)", cmd)
            hb_port = int(hb_match.group(1)) if hb_match else None

            return {
                "pid": data.get("pid"),
                "cmd": cmd,
                "ports": ports,
                "csrf_token": csrf_token,
                "host_bridge_port": hb_port,
            }
        except Exception as exc:
            logger.warning("Dynamic language_server process discovery failed: %s", exc)
            return None

    def resolve_credentials(
        self,
        cli_path: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Resolves the active (address, csrf_token) for the Antigravity Language Server.
        Follows a strict 3-tier hierarchy:
          1. Validated cache (if within TTL and not force_refresh).
          2. Environment variables (ANTIGRAVITY_LS_ADDRESS, ANTIGRAVITY_CSRF_TOKEN).
          3. Pydantic application settings (.env configuration).
          4. Autonomous dynamic process inspection and port probing.
        """
        from app.config import get_settings
        settings = get_settings()

        if not cli_path:
            cli_path = settings.ANTIGRAVITY_AGENTAPI_PATH

        now = time.monotonic()
        if (
            not force_refresh
            and self._cached_address
            and self._cached_token
            and (now - self._cached_at < self._cache_ttl_seconds)
        ):
            return self._cached_address, self._cached_token

        # Tier 1: Check existing OS environment variables
        env_addr = os.environ.get("ANTIGRAVITY_LS_ADDRESS")
        env_token = os.environ.get("ANTIGRAVITY_CSRF_TOKEN")
        if env_addr:
            if self.verify_credentials(cli_path, env_addr, env_token):
                self._cached_address = env_addr
                self._cached_token = env_token or ""
                self._cached_at = now
                logger.info("Using verified Antigravity credentials from OS environment: %s", env_addr)
                return self._cached_address, self._cached_token

        # Tier 2: Check settings / .env configuration
        cfg_addr = getattr(settings, "ANTIGRAVITY_LS_ADDRESS", None)
        cfg_token = getattr(settings, "ANTIGRAVITY_CSRF_TOKEN", None)
        if cfg_addr:
            token = cfg_token or env_token or ""
            if self.verify_credentials(cli_path, cfg_addr, token):
                self._cached_address = cfg_addr
                self._cached_token = token
                self._cached_at = now
                logger.info("Using verified Antigravity credentials from config/.env: %s", cfg_addr)
                return self._cached_address, self._cached_token

        # Tier 3: Autonomous dynamic process discovery
        auto_discover = getattr(settings, "ANTIGRAVITY_AUTO_DISCOVER", True)
        if auto_discover:
            logger.info("Initiating autonomous dynamic discovery for Antigravity Language Server...")
            proc_info = self._discover_from_process()
            if proc_info:
                discovered_token = proc_info.get("csrf_token") or env_token or cfg_token or ""
                ports: List[int] = proc_info.get("ports", [])  # type: ignore[assignment]
                hb_port = proc_info.get("host_bridge_port")

                # Candidate ordering: prioritize host_bridge_port + 2 (standard gRPC port), then other ports
                candidates: List[int] = []
                if hb_port and (hb_port + 2) in ports:
                    candidates.append(hb_port + 2)
                for p in sorted(ports, reverse=True):
                    if p not in candidates:
                        candidates.append(p)

                for port in candidates:
                    addr = f"127.0.0.1:{port}"
                    if self.verify_credentials(cli_path, addr, discovered_token):
                        self._cached_address = addr
                        self._cached_token = discovered_token
                        self._cached_at = now
                        logger.info(
                            "Autonomous discovery SUCCESS: Connected to Antigravity Language Server on %s (PID: %s)",
                            addr,
                            proc_info.get("pid"),
                        )
                        return addr, discovered_token

        logger.error(
            "Could not discover or verify a running Antigravity Language Server. "
            "Ensure Google Antigravity is running."
        )
        return None, None

    def get_subprocess_env(
        self,
        workspace_path: Optional[str] = None,
        cli_path: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Builds a complete, enriched environment dictionary for spawning AgentAPI subprocesses.
        Injects ANTIGRAVITY_LS_ADDRESS, ANTIGRAVITY_CSRF_TOKEN, ANTIGRAVITY_APP_DATA_DIR, and ANTIGRAVITY_AGENT.
        """
        from app.config import get_settings
        settings = get_settings()

        addr, token = self.resolve_credentials(cli_path=cli_path)
        if not addr:
            raise RuntimeError(
                "ANTIGRAVITY_LS_ADDRESS could not be determined. "
                "The Antigravity Language Server does not appear to be running. "
                "Please launch Antigravity or configure ANTIGRAVITY_LS_ADDRESS in .env."
            )

        env = os.environ.copy()
        env["ANTIGRAVITY_LS_ADDRESS"] = addr
        if token:
            env["ANTIGRAVITY_CSRF_TOKEN"] = token
        env["ANTIGRAVITY_AGENT"] = "1"

        # Provide standard app data directory
        app_data_dir = getattr(settings, "ANTIGRAVITY_APP_DATA_DIR", None)
        if not app_data_dir:
            from pathlib import Path
            app_data_dir = str(Path.home() / ".gemini" / "antigravity")
        env["ANTIGRAVITY_APP_DATA_DIR"] = app_data_dir

        return env


# Global singleton discovery instance
antigravity_discovery = AntigravityDiscoveryService()
