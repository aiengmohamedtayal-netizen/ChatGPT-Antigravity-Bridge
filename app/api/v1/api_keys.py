"""API Key management router for generating and revoking credentials."""

from datetime import datetime, timedelta, timezone
from typing import List
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.api_key import ApiKey, ApiScope
from app.schemas.api_key import ApiKeyCreate, ApiKeyResponse, ApiKeyCreated
from app.core.security import generate_api_key
from app.core.dependencies import get_current_api_key, require_scopes, get_client_ip
from app.core.audit import record_audit_event
from app.core.errors import NotFoundError

router = APIRouter(prefix="/api-keys", tags=["API Keys & Credentials"])


@router.get("", response_model=List[ApiKeyResponse], summary="List API Keys")
async def list_api_keys(
    api_key: ApiKey = Depends(require_scopes([ApiScope.ADMIN])),
    db: Session = Depends(get_db),
):
    keys = db.query(ApiKey).order_by(ApiKey.created_at.desc()).all()
    return [ApiKeyResponse.model_validate(k) for k in keys]


@router.post("", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED, summary="Create API Key")
async def create_new_api_key(
    payload: ApiKeyCreate,
    request: Request,
    api_key: ApiKey = Depends(require_scopes([ApiScope.ADMIN])),
    db: Session = Depends(get_db),
):
    raw_key, hashed_key, key_prefix = generate_api_key()

    expires_at = None
    if payload.expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days)

    new_key = ApiKey(
        name=payload.name,
        key_prefix=key_prefix,
        hashed_key=hashed_key,
        scopes=payload.scopes or [ApiScope.TASKS_CREATE, ApiScope.TASKS_READ, ApiScope.PROJECTS_READ],
        is_active=True,
        expires_at=expires_at,
    )
    db.add(new_key)
    db.commit()
    db.refresh(new_key)

    record_audit_event(
        db=db,
        actor=api_key.name,
        action="API_KEY_CREATE",
        resource_type="api_key",
        resource_id=new_key.id,
        ip_address=get_client_ip(request),
        details={"name": new_key.name, "scopes": new_key.scopes},
    )

    created_resp = ApiKeyCreated(
        id=new_key.id,
        name=new_key.name,
        key_prefix=new_key.key_prefix,
        scopes=new_key.scopes,
        is_active=new_key.is_active,
        created_at=new_key.created_at,
        expires_at=new_key.expires_at,
        raw_key=raw_key,
    )
    return created_resp


@router.delete("/{key_id}", summary="Revoke API Key")
async def revoke_api_key(
    key_id: str,
    request: Request,
    api_key: ApiKey = Depends(require_scopes([ApiScope.ADMIN])),
    db: Session = Depends(get_db),
):
    target = db.query(ApiKey).filter(ApiKey.id == key_id).first()
    if not target:
        raise NotFoundError(detail=f"API key '{key_id}' not found.", code="KEY_NOT_FOUND")

    target.is_active = False
    db.commit()

    record_audit_event(
        db=db,
        actor=api_key.name,
        action="API_KEY_REVOKE",
        resource_type="api_key",
        resource_id=key_id,
        ip_address=get_client_ip(request),
    )

    return {"success": True, "message": f"API key '{key_id}' has been deactivated."}
