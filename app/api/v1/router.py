"""API v1 master router aggregating all domain subrouters."""

from fastapi import APIRouter
from app.api.v1.tasks import router as tasks_router
from app.api.v1.projects import router as projects_router
from app.api.v1.system import router as system_router
from app.api.v1.api_keys import router as api_keys_router
from app.api.v1.audit import router as audit_router
from app.api.v1.chatgpt import router as chatgpt_router
from app.api.v1.sessions import router as sessions_router
from app.api.v1.workspaces import router as workspaces_router

v1_router = APIRouter(prefix="/api/v1")

v1_router.include_router(workspaces_router)
v1_router.include_router(tasks_router)
v1_router.include_router(projects_router)
v1_router.include_router(sessions_router)
v1_router.include_router(system_router)
v1_router.include_router(api_keys_router)
v1_router.include_router(audit_router)
v1_router.include_router(chatgpt_router)
