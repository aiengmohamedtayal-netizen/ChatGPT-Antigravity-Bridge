"""Remote and Stdio Model Context Protocol (MCP) Server and lifecycle manager."""

import asyncio
import json
import logging
import sys
import uuid
from typing import Any, Dict, Optional
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from app.config import get_settings
from app.core.telemetry import get_correlation_id, set_correlation_id
from app.mcp.protocol import (
    JSONRPC_VERSION,
    MCP_PROTOCOL_VERSION,
    JsonRpcError,
    JsonRpcRequest,
    JsonRpcResponse,
)
from app.mcp.tools import MCP_TOOLS, execute_mcp_tool

logger = logging.getLogger("antigravity.mcp")
mcp_router = APIRouter(prefix="/mcp", tags=["Model Context Protocol (MCP)"])

# Active SSE sessions for Remote MCP
_active_sse_queues: Dict[str, asyncio.Queue] = {}


class McpBridgeRuntime:
    """
    Manages the ChatGPT MCP Bridge background lifecycle, active SSE session queues,
    and graceful teardown alongside Antigravity Core.
    """

    def __init__(self) -> None:
        self._shutdown_event: Optional[asyncio.Event] = None
        self._monitor_task: Optional[asyncio.Task] = None
        self._is_running: bool = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def active_session_count(self) -> int:
        return len(_active_sse_queues)

    def _get_shutdown_event(self) -> asyncio.Event:
        if self._shutdown_event is None:
            self._shutdown_event = asyncio.Event()
        return self._shutdown_event

    async def start(self) -> None:
        """Start the non-blocking MCP Bridge background session monitor task."""
        if self._is_running:
            return
        self._shutdown_event = asyncio.Event()
        self._is_running = True
        self._monitor_task = asyncio.create_task(
            self._session_keepalive_loop(),
            name="chatgpt-mcp-bridge-monitor",
        )
        logger.info(
            "ChatGPT MCP Bridge background service online (tools=%d).",
            len(MCP_TOOLS),
            extra={"event": "mcp_bridge_started", "tools_count": len(MCP_TOOLS)},
        )

    async def stop(self) -> None:
        """Gracefully drain all active MCP SSE streams and stop the background monitor."""
        if not self._is_running:
            return
        self._is_running = False
        if self._shutdown_event is not None:
            self._shutdown_event.set()

        # Notify all open SSE streams to terminate immediately so ports never hang
        for session_id, queue in list(_active_sse_queues.items()):
            try:
                queue.put_nowait(None)
            except Exception:
                pass
        _active_sse_queues.clear()

        if self._monitor_task is not None:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

        logger.info(
            "ChatGPT MCP Bridge shut down cleanly.",
            extra={"event": "mcp_bridge_stopped"},
        )

    async def _session_keepalive_loop(self) -> None:
        """Background task maintaining MCP bridge state until shutdown signal."""
        shutdown_ev = self._get_shutdown_event()
        try:
            while self._is_running and not shutdown_ev.is_set():
                await asyncio.sleep(15.0)
        except asyncio.CancelledError:
            pass


mcp_bridge_runtime = McpBridgeRuntime()


async def process_json_rpc(request_data: Dict[str, Any], db: Optional[Any] = None) -> JsonRpcResponse:
    """Core JSON-RPC 2.0 / MCP message dispatcher with structured exception safety."""
    cid = get_correlation_id()
    try:
        rpc_req = JsonRpcRequest.model_validate(request_data)
    except Exception as e:
        return JsonRpcResponse(
            error=JsonRpcError(
                code=-32600,
                message=f"Invalid Request: {str(e)}",
                data={"correlation_id": cid},
            )
        )

    method = rpc_req.method
    params = rpc_req.params or {}
    req_id = rpc_req.id

    try:
        if method == "initialize":
            settings = get_settings()
            return JsonRpcResponse(
                id=req_id,
                result={
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "serverInfo": {
                        "name": settings.MCP_SERVER_NAME,
                        "version": settings.MCP_SERVER_VERSION,
                    },
                    "capabilities": {
                        "tools": {"listChanged": True},
                        "resources": {"subscribe": False, "listChanged": False},
                        "prompts": {"listChanged": False},
                    },
                },
            )

        elif method == "notifications/initialized":
            return JsonRpcResponse(id=req_id, result={})

        elif method == "ping":
            return JsonRpcResponse(id=req_id, result={})

        elif method == "tools/list":
            tools_dict = [t.model_dump() for t in MCP_TOOLS]
            return JsonRpcResponse(id=req_id, result={"tools": tools_dict})

        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})
            result = await execute_mcp_tool(tool_name, tool_args, db=db)
            return JsonRpcResponse(id=req_id, result=result.model_dump())

        else:
            return JsonRpcResponse(
                id=req_id,
                error=JsonRpcError(
                    code=-32601,
                    message=f"Method '{method}' not found",
                    data={"correlation_id": cid},
                ),
            )
    except Exception as exc:
        logger.exception(
            "Unhandled error in MCP JSON-RPC method '%s': %s",
            method,
            exc,
            extra={"event": "mcp_jsonrpc_error", "method": method, "correlation_id": cid},
        )
        return JsonRpcResponse(
            id=req_id,
            error=JsonRpcError(
                code=-32603,
                message="Internal MCP Server Error",
                data={"detail": str(exc), "correlation_id": cid},
            ),
        )


# ==========================================
# Remote MCP Endpoints (HTTP + SSE)
# ==========================================

@mcp_router.get("/sse")
async def mcp_sse_endpoint(request: Request):
    """
    Standard MCP SSE Transport Endpoint.
    Antigravity or any MCP client connects here to establish an SSE channel.
    """
    session_id = f"mcp_sess_{uuid.uuid4().hex[:12]}"
    queue: asyncio.Queue = asyncio.Queue()
    _active_sse_queues[session_id] = queue

    async def event_generator():
        try:
            proto = request.headers.get("x-forwarded-proto", request.url.scheme)
            host = request.headers.get("x-forwarded-host", request.headers.get("host", ""))
            if host:
                endpoint_url = f"{proto}://{host}/mcp/messages?session_id={session_id}"
            else:
                endpoint_url = f"/mcp/messages?session_id={session_id}"
            yield f"event: endpoint\ndata: {endpoint_url}\n\n"

            while mcp_bridge_runtime.is_running or not mcp_bridge_runtime._get_shutdown_event().is_set():
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=15.0)
                    if data is None:
                        # Shutdown sentinel received
                        break
                    yield f"event: message\ndata: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            _active_sse_queues.pop(session_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@mcp_router.options("/sse")
@mcp_router.head("/sse")
async def mcp_sse_probe():
    return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "ok"})


@mcp_router.post("/messages")
@mcp_router.post("/sse")
async def mcp_messages_endpoint(request: Request):
    """
    Receives JSON-RPC payload from MCP client.
    Supports both /mcp/messages and direct POST /mcp/sse.
    """
    session_id = request.query_params.get("session_id")
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ready", "mcp": "available"},
        )

    response = await process_json_rpc(body)
    resp_dict = response.model_dump(exclude_none=True)

    if session_id and session_id in _active_sse_queues:
        await _active_sse_queues[session_id].put(resp_dict)
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={"status": "accepted"})

    return JSONResponse(status_code=status.HTTP_200_OK, content=resp_dict)


# ==========================================
# Stdio Server Runner (For CLI Antigravity)
# ==========================================

async def run_stdio_server():
    """Run MCP server over stdio (compatible with Antigravity mcp_config.json)."""
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    w_transport, w_protocol = await loop.connect_write_pipe(asyncio.streams.FlowControlMixin, sys.stdout)
    writer = asyncio.StreamWriter(w_transport, w_protocol, reader, loop)

    while True:
        line = await reader.readline()
        if not line:
            break
        try:
            set_correlation_id()
            req_data = json.loads(line.decode("utf-8"))
            resp = await process_json_rpc(req_data)
            out_bytes = json.dumps(resp.model_dump(exclude_none=True)).encode("utf-8") + b"\n"
            writer.write(out_bytes)
            await writer.drain()
        except Exception as e:
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32603,
                    "message": str(e),
                    "data": {"correlation_id": get_correlation_id()},
                },
            }
            writer.write(json.dumps(err_resp).encode("utf-8") + b"\n")
            await writer.drain()


if __name__ == "__main__":
    asyncio.run(run_stdio_server())

