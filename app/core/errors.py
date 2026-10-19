"""Error handling, custom exception types, RFC 7807 Problem Details, and MCP JSON-RPC 2.0 error envelopes."""

import logging
from typing import Any, Dict, Optional
from fastapi import Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.telemetry import get_correlation_id

logger = logging.getLogger("antigravity.errors")


class ProblemDetail(BaseModel):
    """RFC 7807 compliant problem details response."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: Optional[str] = None
    code: Optional[str] = None
    correlation_id: Optional[str] = None
    invalid_params: Optional[list] = None
    extra: Optional[Dict[str, Any]] = None


class BridgeException(Exception):
    """Base application exception."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "INTERNAL_ERROR"
    title: str = "Internal Server Error"
    jsonrpc_code: int = -32603

    def __init__(
        self,
        detail: str,
        code: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(detail)
        self.detail = detail
        if code:
            self.code = code
        self.extra = extra or {}


class AuthenticationError(BridgeException):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "AUTHENTICATION_FAILED"
    title = "Authentication Failed"
    jsonrpc_code = -32001


class AuthorizationError(BridgeException):
    status_code = status.HTTP_403_FORBIDDEN
    code = "INSUFFICIENT_PERMISSIONS"
    title = "Permission Denied"
    jsonrpc_code = -32003


class NotFoundError(BridgeException):
    status_code = status.HTTP_404_NOT_FOUND
    code = "RESOURCE_NOT_FOUND"
    title = "Resource Not Found"
    jsonrpc_code = -32004


class BadRequestError(BridgeException):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "BAD_REQUEST"
    title = "Bad Request"
    jsonrpc_code = -32602


class ConflictError(BridgeException):
    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"
    title = "Conflict"
    jsonrpc_code = -32009


class RateLimitExceededError(BridgeException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "RATE_LIMIT_EXCEEDED"
    title = "Rate Limit Exceeded"
    jsonrpc_code = -32029


class ProviderError(BridgeException):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "PROVIDER_UNAVAILABLE"
    title = "Agent Provider Error"
    jsonrpc_code = -32052


class ExecutionTimeoutError(BridgeException):
    status_code = status.HTTP_504_GATEWAY_TIMEOUT
    code = "EXECUTION_TIMEOUT"
    title = "Gateway Execution Timeout"
    jsonrpc_code = -32000


def format_jsonrpc_error_payload(
    code: int,
    message: str,
    correlation_id: str,
    detail: Optional[str] = None,
    status_code: int = 500,
    error_code: str = "INTERNAL_ERROR",
    instance: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a dual-compatible JSON-RPC 2.0 + RFC 7807 error envelope."""
    return {
        "jsonrpc": "2.0",
        "id": None,
        "error": {
            "code": code,
            "message": message,
            "data": {
                "code": error_code,
                "detail": detail or message,
                "correlation_id": correlation_id,
                "instance": instance,
            },
        },
        "type": f"https://antigravity.dev/errors/{error_code.lower()}",
        "title": message,
        "status": status_code,
        "detail": detail or message,
        "code": error_code,
        "correlation_id": correlation_id,
        "instance": instance,
    }


async def bridge_exception_handler(request: Request, exc: BridgeException) -> JSONResponse:
    """FastAPI exception handler converting BridgeException into RFC 7807 / MCP JSON."""
    cid = get_correlation_id()
    problem = ProblemDetail(
        type=f"https://antigravity.dev/errors/{exc.code.lower()}",
        title=exc.title,
        status=exc.status_code,
        detail=exc.detail,
        instance=str(request.url.path),
        code=exc.code,
        correlation_id=cid,
        extra=exc.extra or None,
    )
    headers = {
        "X-Request-ID": cid,
        "X-Correlation-ID": cid,
    }
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        headers["WWW-Authenticate"] = "Bearer"

    content = problem.model_dump(exclude_none=True)
    if request.url.path.startswith("/mcp"):
        content["jsonrpc"] = "2.0"
        content["id"] = None
        content["error"] = {
            "code": exc.jsonrpc_code,
            "message": exc.title,
            "data": {
                "code": exc.code,
                "detail": exc.detail,
                "correlation_id": cid,
            },
        }

    return JSONResponse(
        status_code=exc.status_code,
        content=content,
        headers=headers,
    )


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global catch-all exception handler formatting unhandled errors into MCP/JSON-RPC 2.0 & RFC 7807 responses."""
    cid = get_correlation_id()
    logger.exception(
        "Unhandled server exception on %s %s",
        request.method,
        request.url.path,
        extra={
            "event": "unhandled_exception",
            "method": request.method,
            "path": request.url.path,
            "error_type": type(exc).__name__,
        },
    )
    payload = format_jsonrpc_error_payload(
        code=-32603,
        message="Internal Server Error",
        correlation_id=cid,
        detail="An unexpected internal error occurred while processing the request.",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code="INTERNAL_ERROR",
        instance=str(request.url.path),
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=payload,
        headers={
            "X-Request-ID": cid,
            "X-Correlation-ID": cid,
        },
    )

