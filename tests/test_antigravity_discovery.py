"""
Unit and Integration Tests for Antigravity Language Server Dynamic Discovery Service.
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from app.services.antigravity_discovery import AntigravityDiscoveryService


def test_verify_credentials_unreachable():
    """Verify that probing an invalid or closed port correctly returns False."""
    service = AntigravityDiscoveryService()
    cli_path = r"C:\Users\Click Labtop\.gemini\antigravity\bin\agentapi.bat"
    # Port 59999 is closed
    is_valid = service.verify_credentials(cli_path, "127.0.0.1:59999", "dummy_token")
    assert is_valid is False


def test_verify_credentials_missing_cli():
    """Verify that a nonexistent CLI binary returns False without throwing."""
    service = AntigravityDiscoveryService()
    is_valid = service.verify_credentials("nonexistent_agentapi.bat", "127.0.0.1:64712", "dummy_token")
    assert is_valid is False


def test_resolve_credentials_from_env(monkeypatch):
    """Verify that credentials present in os.environ are detected and resolved."""
    service = AntigravityDiscoveryService()
    monkeypatch.setenv("ANTIGRAVITY_LS_ADDRESS", "localhost:64712")
    monkeypatch.setenv("ANTIGRAVITY_CSRF_TOKEN", "e3a35322-dfb5-4ee6-ba67-a873dd0aac5a")

    with patch.object(service, "verify_credentials", return_value=True):
        addr, token = service.resolve_credentials(force_refresh=True)
        assert addr == "localhost:64712"
        assert token == "e3a35322-dfb5-4ee6-ba67-a873dd0aac5a"


def test_cache_invalidation():
    """Verify that invalidate_cache clears cached address and token."""
    service = AntigravityDiscoveryService()
    service._cached_address = "localhost:64712"
    service._cached_token = "dummy_token"
    service._cached_at = 999999999.0

    service.invalidate_cache()
    assert service._cached_address is None
    assert service._cached_token is None
    assert service._cached_at == 0.0


def test_get_subprocess_env(monkeypatch):
    """Verify that get_subprocess_env enriches the environment with all needed variables."""
    service = AntigravityDiscoveryService()
    with patch.object(service, "resolve_credentials", return_value=("127.0.0.1:64712", "mock_token")):
        env = service.get_subprocess_env()
        assert env["ANTIGRAVITY_LS_ADDRESS"] == "127.0.0.1:64712"
        assert env["ANTIGRAVITY_CSRF_TOKEN"] == "mock_token"
        assert env["ANTIGRAVITY_AGENT"] == "1"
        assert "ANTIGRAVITY_APP_DATA_DIR" in env


def test_get_subprocess_env_raises_when_unreachable():
    """Verify that get_subprocess_env raises a clear RuntimeError if LS cannot be resolved."""
    service = AntigravityDiscoveryService()
    with patch.object(service, "resolve_credentials", return_value=(None, None)):
        with pytest.raises(RuntimeError, match="ANTIGRAVITY_LS_ADDRESS could not be determined"):
            service.get_subprocess_env()


@pytest.mark.asyncio
async def test_antigravity_real_provider_health_check():
    """Verify AntigravityRealAgentProvider.check_health reports connected when LS is verified."""
    from app.providers.antigravity_real import AntigravityRealAgentProvider
    provider = AntigravityRealAgentProvider()

    with patch("app.services.antigravity_discovery.antigravity_discovery.resolve_credentials", return_value=("localhost:64712", "valid_token")):
        health = await provider.check_health()
        assert health["status"] == "connected"
        assert "64712" in health["message"] or health.get("ls_address") == "localhost:64712"


@pytest.mark.asyncio
async def test_real_agent_session_creation_with_discovery():
    """Verify AntigravityRealAgentProvider.create_session uses discovered env and succeeds."""
    from app.providers.antigravity_real import AntigravityRealAgentProvider
    provider = AntigravityRealAgentProvider()

    # Pass an already existing workspace or D:\REZAN
    workspace = r"D:\REZAN" if os.path.exists(r"D:\REZAN") else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Test that create_session resolves credentials and can create a session
    cid = await provider.create_session(workspace_path=workspace)
    assert cid is not None
    assert len(cid) > 0
    # Conversation IDs are typically UUIDs (e.g. 36 chars) or formatted IDs
    assert "-" in cid
