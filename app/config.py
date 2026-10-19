"""Application configuration module using Pydantic Settings."""

import os
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_agentapi_path() -> str:
    user_home = Path.home()
    if os.name == "nt":
        return str(user_home / ".gemini" / "antigravity" / "bin" / "agentapi.bat")
    return str(user_home / ".gemini" / "antigravity" / "bin" / "agentapi")


def _default_brain_dir() -> str:
    return str(Path.home() / ".gemini" / "antigravity" / "brain")


class Settings(BaseSettings):
    """Bridge application settings and environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "ChatGPT × Antigravity Bridge"
    APP_VERSION: str = "1.0.0"
    APP_DESCRIPTION: str = (
        "Secure developer tool connecting ChatGPT (Architect/Orchestrator) with "
        "Google Antigravity (Implementation Agent) via native MCP and AgentAPI."
    )
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Master Secret for API Key Hashing and AES Credential Encryption
    BRIDGE_SECRET_KEY: str = "agb_master_secret_key_32_bytes_safe_dev_fallback_123!"

    # Database Settings
    DATABASE_URL: str = "sqlite:///./bridge_data.db"

    # Agent Providers
    DEFAULT_AGENT_PROVIDER: str = "antigravity"
    ANTIGRAVITY_AGENTAPI_PATH: str = Field(default_factory=_default_agentapi_path)
    ANTIGRAVITY_BRAIN_DIR: str = Field(default_factory=_default_brain_dir)
    ANTIGRAVITY_LANGUAGE_SERVER_PORT: int = 58045
    ANTIGRAVITY_LS_ADDRESS: Optional[str] = None
    ANTIGRAVITY_CSRF_TOKEN: Optional[str] = None
    ANTIGRAVITY_AUTO_DISCOVER: bool = True

    # Rate Limiting & Timeouts
    RATE_LIMIT_DEFAULT: str = "120/minute"
    RATE_LIMIT_TASK_CREATE: str = "30/minute"
    REQUEST_TIMEOUT_SECONDS: float = 30.0
    MCP_TOOL_TIMEOUT_SECONDS: float = 25.0
    STRUCTURED_JSON_LOGS: bool = True

    # Security & CORS
    CORS_ORIGINS: Union[str, List[str]] = "*"
    ENABLE_CSRF_PROTECTION: bool = False

    # Outbound OpenAI (Optional)
    OPENAI_API_KEY: str = ""

    # Workspace Authorization & Multi-Root Management
    WORKSPACES_CONFIG_FILE: str = "workspaces.json"
    AUTHORIZED_WORKSPACES: Optional[str] = None  # Comma-separated paths or JSON string from env
    ALLOW_DRIVE_ROOTS: bool = False  # When True, permits registering full drive roots (e.g. D:\)
    RESTRICTED_SYSTEM_DIRECTORIES: List[str] = [
        "c:\\windows",
        "c:\\program files",
        "c:\\program files (x86)",
        "c:\\users\\default",
        "c:\\users\\all users",
        "/etc",
        "/usr",
        "/bin",
        "/sbin",
        "/root",
    ]

    # MCP Server configuration
    MCP_SERVER_NAME: str = "antigravity-bridge"
    MCP_SERVER_VERSION: str = "1.0.0"
    MCP_SSE_ENDPOINT: str = "/mcp/sse"
    MCP_MESSAGES_ENDPOINT: str = "/mcp/messages"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            if v.strip() == "*":
                return ["*"]
            return [i.strip() for i in v.split(",") if i.strip()]
        return v


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
