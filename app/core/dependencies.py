"""FastAPI dependencies for authentication, authorization, and request context."""

from datetime import datetime, timezone
from typing import List, Optional
from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.api_key import ApiKey, ApiScope
from app.core.errors import AuthenticationError, AuthorizationError
from app.core.security import hash_api_key

security_scheme = HTTPBearer(auto_error=False)


async def get_current_api_key(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> ApiKey:
    """Validate Bearer API key against the database."""
    # Allow querying with x-api-key header as well
    raw_token = None
    if credentials and credentials.credentials:
        raw_token = credentials.credentials
    elif "x-api-key" in request.headers:
        raw_token = request.headers["x-api-key"]

    if not raw_token:
        raise AuthenticationError(
            detail="Missing Bearer API Key in Authorization header or x-api-key header",
            code="MISSING_API_KEY",
        )

    # Compute hash and query
    hashed = hash_api_key(raw_token)
    api_key = db.query(ApiKey).filter(ApiKey.hashed_key == hashed, ApiKey.is_active.is_(True)).first()

    if not api_key:
        raise AuthenticationError(
            detail="Invalid, revoked, or non-existent API Key",
            code="INVALID_API_KEY",
        )

    # Check expiration
    if api_key.expires_at:
        expires_at = api_key.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            raise AuthenticationError(
                detail="API Key has expired",
                code="EXPIRED_API_KEY",
            )

    # Update last used timestamp
    api_key.last_used_at = datetime.now(timezone.utc)
    db.commit()

    return api_key


def require_scopes(required_scopes: List[str]):
    """Decorator dependency to enforce RBAC scopes on an endpoint."""

    async def scope_checker(api_key: ApiKey = Depends(get_current_api_key)) -> ApiKey:
        key_scopes = api_key.scopes or []
        if ApiScope.ADMIN in key_scopes:
            return api_key

        for req in required_scopes:
            if req not in key_scopes:
                raise AuthorizationError(
                    detail=f"API Key lacks required permission scope: {req}",
                    code="INSUFFICIENT_SCOPE",
                    extra={"required_scope": req, "granted_scopes": key_scopes},
                )
        return api_key

    return scope_checker


def get_client_ip(request: Request) -> str:
    """Safely extract remote client IP."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def get_idempotency_key(
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> Optional[str]:
    """Extract optional Idempotency-Key header."""
    return idempotency_key
