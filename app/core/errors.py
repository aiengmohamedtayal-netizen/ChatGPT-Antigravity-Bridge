"""Error handling, custom exception types, and RFC 7807 Problem Details."""

from typing import Any, Dict, Optional
from fastapi import Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ProblemDetail(BaseModel):
    """RFC 7807 compliant problem details response."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: Optional[str] = None
    code: Optional[str] = None
    invalid_params: Optional[list] = None
    extra: Optional[Dict[str, Any]] = None


class BridgeException(Exception):
    """Base application exception."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "INTERNAL_ERROR"
    title: str = "Internal Server Error"

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


class AuthorizationError(BridgeException):
    status_code = status.HTTP_403_FORBIDDEN
    code = "INSUFFICIENT_PERMISSIONS"
    title = "Permission Denied"


class NotFoundError(BridgeException):
    status_code = status.HTTP_404_NOT_FOUND
    code = "RESOURCE_NOT_FOUND"
    title = "Resource Not Found"


class BadRequestError(BridgeException):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "BAD_REQUEST"
    title = "Bad Request"


class ConflictError(BridgeException):
    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"
    title = "Conflict"


class RateLimitExceededError(BridgeException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "RATE_LIMIT_EXCEEDED"
    title = "Rate Limit Exceeded"


class ProviderError(BridgeException):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "PROVIDER_UNAVAILABLE"
    title = "Agent Provider Error"


async def bridge_exception_handler(request: Request, exc: BridgeException) -> JSONResponse:
    """FastAPI exception handler converting BridgeException into RFC 7807 JSON."""
    problem = ProblemDetail(
        type=f"https://antigravity.dev/errors/{exc.code.lower()}",
        title=exc.title,
        status=exc.status_code,
        detail=exc.detail,
        instance=str(request.url.path),
        code=exc.code,
        extra=exc.extra or None,
    )
    headers = {}
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        headers["WWW-Authenticate"] = "Bearer"

    return JSONResponse(
        status_code=exc.status_code,
        content=problem.model_dump(exclude_none=True),
        headers=headers,
    )
