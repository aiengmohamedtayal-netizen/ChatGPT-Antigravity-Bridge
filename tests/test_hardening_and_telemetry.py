"""Tests for unified runtime lifecycle, telemetry, strict Accept negotiation, and global exception handling."""

import json
import logging
import pytest

from app.core.telemetry import (
    StructuredJsonFormatter,
    set_correlation_id,
    telemetry,
)
from app.mcp.server import mcp_bridge_runtime, process_json_rpc
from app.orchestration.orchestrator import orchestrator
from main import UnifiedBridgeRunner


def test_strict_accept_header_negotiation(client):
    """Verify automated clients always receive JSON while interactive browsers receive HTML."""
    # 1. Default TestClient (*/*) -> strict JSON
    res_default = client.get("/")
    assert res_default.status_code == 200
    assert "application/json" in res_default.headers["content-type"]
    assert res_default.json()["status"] == "healthy"

    # 2. Explicit application/json -> strict JSON
    res_json = client.get("/", headers={"Accept": "application/json"})
    assert res_json.status_code == 200
    assert "application/json" in res_json.headers["content-type"]

    # 3. Equal priority text/html and application/json -> strict JSON
    res_equal = client.get("/", headers={"Accept": "text/html, application/json"})
    assert res_equal.status_code == 200
    assert "application/json" in res_equal.headers["content-type"]

    # 4. Browser Accept header BUT carrying API credentials -> strict JSON
    res_auth = client.get(
        "/",
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Authorization": "Bearer agb_live_test_token",
        },
    )
    assert res_auth.status_code == 200
    assert "application/json" in res_auth.headers["content-type"]

    # 5. Browser Accept header without API credentials -> HTML view
    res_browser = client.get(
        "/",
        headers={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
    )
    assert res_browser.status_code == 200
    assert "text/html" in res_browser.headers["content-type"]
    assert "ANTIGRAVITY CORE: ONLINE" in res_browser.text
    assert "CHATGPT MCP BRIDGE: ONLINE" in res_browser.text


def test_enhanced_health_telemetry_and_correlation_id(client):
    """Verify /health returns dynamic uptime, memory, component status, and tool metrics."""
    custom_cid = "corr_test_998877"
    response = client.get("/health", headers={"X-Correlation-ID": custom_cid})
    assert response.status_code == 200
    assert response.headers.get("X-Correlation-ID") == custom_cid
    assert response.headers.get("X-Request-ID") == custom_cid

    data = response.json()
    assert data["status"] == "healthy"
    assert data["correlation_id"] == custom_cid
    assert "uptime_seconds" in data
    assert "memory" in data
    assert "rss_mb" in data["memory"]
    assert "components" in data
    assert "antigravity_core" in data["components"]
    assert "chatgpt_mcp_bridge" in data["components"]
    assert "telemetry" in data
    assert "http_requests" in data["telemetry"]
    assert "tool_executions" in data["telemetry"]


@pytest.mark.asyncio
async def test_mcp_tool_telemetry_and_non_blocking_execution(db_session):
    """Verify MCP tool execution updates telemetry counters and preserves correlation IDs."""
    set_correlation_id("cid_mcp_tool_test")
    before = telemetry.snapshot()["tool_executions"]["total"]

    rpc_payload = {
        "jsonrpc": "2.0",
        "id": 42,
        "method": "tools/call",
        "params": {
            "name": "list_workspaces",
            "arguments": {"enabled_only": True},
        },
    }
    resp = await process_json_rpc(rpc_payload, db=db_session)
    assert resp.id == 42
    assert resp.error is None
    assert resp.result is not None

    after = telemetry.snapshot()["tool_executions"]
    assert after["total"] == before + 1
    assert "list_workspaces" in after["by_tool"]
    assert after["by_tool"]["list_workspaces"]["calls"] >= 1


def test_structured_json_formatter():
    """Verify log records serialize into structured JSON with correlation_id."""
    set_correlation_id("cid_json_log_123")
    formatter = StructuredJsonFormatter()
    record = logging.LogRecord(
        name="antigravity.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Test message %s",
        args=("ok",),
        exc_info=None,
    )
    record.event = "unit_test_event"
    formatted = formatter.format(record)
    parsed = json.loads(formatted)
    assert parsed["message"] == "Test message ok"
    assert parsed["correlation_id"] == "cid_json_log_123"
    assert parsed["event"] == "unit_test_event"
    assert parsed["level"] == "INFO"


@pytest.mark.asyncio
async def test_unified_bridge_runner_lifecycle_and_signal_teardown():
    """Verify McpBridgeRuntime, TaskOrchestrator, and UnifiedBridgeRunner start and tear down cleanly."""
    orchestrator.start_worker()
    await mcp_bridge_runtime.start()
    assert orchestrator._is_running is True
    assert mcp_bridge_runtime.is_running is True

    runner = UnifiedBridgeRunner(host="127.0.0.1", port=3000)
    runner._handle_exit_signal("SIGTERM")
    assert runner.shutdown_event.is_set() is True

    await mcp_bridge_runtime.stop()
    await orchestrator.stop_worker()
    assert mcp_bridge_runtime.is_running is False
    assert orchestrator._is_running is False
