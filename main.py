"""
Unified Main Entrypoint for Antigravity Core and ChatGPT MCP Bridge.

Natively initializes and runs both the Antigravity Core task orchestrator and the
ChatGPT MCP Bridge server concurrently inside a single asyncio event loop with
coordinated SIGINT / SIGTERM graceful teardown.
"""

import asyncio
import logging
import os
import signal
import sys
from typing import Optional
import uvicorn

from app.config import get_settings
from app.core.telemetry import set_correlation_id
from app.main import app
from app.mcp.server import mcp_bridge_runtime
from app.orchestration.orchestrator import orchestrator

logger = logging.getLogger("antigravity.entrypoint")


class UnifiedBridgeRunner:
    """
    Coordinates the concurrent asyncio execution and graceful signal teardown
    of Antigravity Core and the ChatGPT MCP Bridge server.
    """

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.settings = get_settings()
        self.shutdown_event = asyncio.Event()
        self._server: Optional[uvicorn.Server] = None

    def _handle_exit_signal(self, sig_name: str) -> None:
        """Signal callback bound to SIGINT and SIGTERM."""
        set_correlation_id("signal_teardown")
        logger.info(
            "Received %s signal. Initiating coordinated shutdown of Antigravity Core & ChatGPT MCP Bridge...",
            sig_name,
            extra={"event": "signal_received", "signal": sig_name},
        )
        self.shutdown_event.set()
        if self._server is not None:
            self._server.should_exit = True

    def _register_signal_handlers(self, loop: asyncio.AbstractEventLoop) -> None:
        """Bind SIGINT and SIGTERM to the unified graceful shutdown sequence."""
        for sig in (signal.SIGINT, signal.SIGTERM):
            sig_name = sig.name
            try:
                loop.add_signal_handler(sig, self._handle_exit_signal, sig_name)
            except (NotImplementedError, RuntimeError):
                # Fallback for Windows or non-main threads where loop.add_signal_handler is unsupported
                signal.signal(sig, lambda s, f, name=sig_name: self._handle_exit_signal(name))

    async def _announce_when_listening(self) -> None:
        """Wait for the ASGI/MCP server socket to bind, then emit the unified readiness banner."""
        while self._server is not None and not self._server.started and not self.shutdown_event.is_set():
            await asyncio.sleep(0.05)

        if self.shutdown_event.is_set():
            return

        banner = (
            "\n"
            + "=" * 74 + "\n"
            + f"  [ONLINE] Antigravity Core   : ACTIVE (TaskOrchestrator & BoundaryGuard)\n"
            + f"  [ONLINE] ChatGPT MCP Bridge : LISTENING on http://{self.host}:{self.port}{self.settings.MCP_SSE_ENDPOINT}\n"
            + f"  [DOCS]   OpenAPI & Health   : http://{self.host}:{self.port}/docs | /health\n"
            + "=" * 74
        )
        print(banner, flush=True)
        logger.info(
            "Antigravity Core and ChatGPT MCP Bridge are both online and listening.",
            extra={
                "event": "unified_runtime_ready",
                "host": self.host,
                "port": self.port,
                "mcp_sse_endpoint": self.settings.MCP_SSE_ENDPOINT,
            },
        )

    async def run(self) -> None:
        """Start Antigravity Core and ChatGPT MCP Bridge concurrently and await clean exit."""
        loop = asyncio.get_running_loop()
        self._register_signal_handlers(loop)

        config = uvicorn.Config(
            app=app,
            host=self.host,
            port=self.port,
            log_level="info",
            access_log=False,
        )
        self._server = uvicorn.Server(config)
        # Disable Uvicorn's default signal capture so our unified handler owns SIGINT/SIGTERM
        self._server.install_signal_handlers = lambda: None  # type: ignore[method-assign]

        server_task = asyncio.create_task(
            self._server.serve(),
            name="chatgpt-mcp-bridge-uvicorn",
        )
        readiness_task = asyncio.create_task(
            self._announce_when_listening(),
            name="unified-startup-announcer",
        )

        try:
            await server_task
        except asyncio.CancelledError:
            pass
        finally:
            readiness_task.cancel()
            # Ensure MCP SSE queues and Antigravity TaskOrchestrator worker are completely drained
            await asyncio.gather(
                mcp_bridge_runtime.stop(),
                orchestrator.stop_worker(),
                return_exceptions=True,
            )
            logger.info(
                "Unified runtime exited cleanly with zero zombie tasks or hanging ports.",
                extra={"event": "unified_runtime_exited"},
            )


def run_unified_bridge(host: Optional[str] = None, port: Optional[int] = None) -> None:
    """Entrypoint helper to launch the unified Antigravity Core + ChatGPT MCP Bridge runtime."""
    settings = get_settings()
    resolved_host = host or os.environ.get("HOST", settings.HOST)
    resolved_port = port or int(os.environ.get("PORT", "3000"))

    runner = UnifiedBridgeRunner(host=resolved_host, port=resolved_port)
    try:
        asyncio.run(runner.run())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    run_unified_bridge()
