"""ChatGPT Custom GPT Action Manifest and Integration Assistant."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from app.config import get_settings

router = APIRouter(prefix="/chatgpt", tags=["ChatGPT Integration"])


@router.get("/openapi.json", summary="OpenAPI 3.1 Spec for ChatGPT Actions")
async def get_chatgpt_openapi_spec(request: Request):
    """
    Returns a sanitized, action-ready OpenAPI 3.1 specification specifically
    formatted for direct import into OpenAI's Custom GPT Action editor.
    """
    settings = get_settings()
    # Determine base server URL from incoming request
    base_url = str(request.base_url).rstrip("/")

    spec = {
        "openapi": "3.1.0",
        "info": {
            "title": "ChatGPT ↔ Antigravity Access Gateway API",
            "description": "Secure programmatic gateway giving ChatGPT controlled access to inspect workspaces, manage agent sessions, and execute tasks with Google Antigravity.",
            "version": settings.APP_VERSION,
        },
        "servers": [{"url": base_url}],
        "paths": {
            "/api/v1/projects": {
                "get": {
                    "operationId": "listProjects",
                    "summary": "List authorized Antigravity projects",
                    "description": "Returns list of explicitly authorized project workspaces.",
                    "responses": {"200": {"description": "List of authorized projects"}},
                }
            },
            "/api/v1/projects/{project_id}": {
                "get": {
                    "operationId": "getProject",
                    "summary": "Get project details & metadata",
                    "parameters": [{"name": "project_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "Project metadata"}},
                }
            },
            "/api/v1/projects/{project_id}/context": {
                "get": {
                    "operationId": "getProjectContext",
                    "summary": "Inspect project context and architecture guidelines",
                    "parameters": [{"name": "project_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "Deep project context"}},
                }
            },
            "/api/v1/projects/{project_id}/sessions": {
                "get": {
                    "operationId": "listAgentSessions",
                    "summary": "List active agent sessions for a project",
                    "parameters": [{"name": "project_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "List of sessions"}},
                },
                "post": {
                    "operationId": "createAgentSession",
                    "summary": "Create a new Antigravity Agent session for a project",
                    "parameters": [{"name": "project_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "requestBody": {
                        "content": {"application/json": {"schema": {"type": "object", "properties": {"title": {"type": "string"}}}}}
                    },
                    "responses": {"201": {"description": "New session created"}},
                }
            },
            "/api/v1/sessions/{session_id}": {
                "get": {
                    "operationId": "getAgentSession",
                    "summary": "Get session details and task history",
                    "parameters": [{"name": "session_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "Session details"}},
                }
            },
            "/api/v1/sessions/{session_id}/messages": {
                "post": {
                    "operationId": "sendMessageToSession",
                    "summary": "Send instruction directly to existing Antigravity session",
                    "parameters": [{"name": "session_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["prompt"],
                                    "properties": {
                                        "prompt": {"type": "string", "description": "Instruction for Antigravity Agent"},
                                        "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"], "default": "normal"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {"201": {"description": "Instruction dispatched"}},
                }
            },
            "/api/v1/tasks": {
                "post": {
                    "operationId": "sendAgentCommand",
                    "summary": "Primary Tool: Dispatch command/task to Antigravity Agent",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["project_id", "prompt"],
                                    "properties": {
                                        "project_id": {"type": "string", "description": "Target project workspace ID"},
                                        "prompt": {"type": "string", "description": "Coding instruction for Antigravity"},
                                        "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"], "default": "normal"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {"201": {"description": "Task queued & dispatched"}},
                }
            },
            "/api/v1/tasks/{task_id}": {
                "get": {
                    "operationId": "getTaskStatus",
                    "summary": "Check status, summary, and changed files of a task",
                    "parameters": [{"name": "task_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "Task status & execution output"}},
                }
            },
            "/api/v1/tasks/{task_id}/continue": {
                "post": {
                    "operationId": "continueSession",
                    "summary": "Continue previous task in the same Antigravity session",
                    "parameters": [{"name": "task_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["prompt"],
                                    "properties": {"prompt": {"type": "string"}},
                                }
                            }
                        },
                    },
                    "responses": {"201": {"description": "Continuation task created"}},
                }
            },
            "/api/v1/system/status": {
                "get": {
                    "operationId": "getSystemStatus",
                    "summary": "Check Gateway and Antigravity Agent connectivity",
                    "responses": {"200": {"description": "Gateway health"}},
                }
            },
        },
        "components": {
            "securitySchemes": {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "API Key (agb_live_...)",
                }
            }
        },
        "security": [{"BearerAuth": []}],
    }
    return JSONResponse(content=spec)


@router.get("/instructions", summary="ChatGPT System Prompt Template")
async def get_chatgpt_instructions():
    """Returns the recommended Custom GPT system prompt for ChatGPT."""
    instructions = (
        "You are the Lead Software Architect coordinating with Google Antigravity via the Bridge.\n\n"
        "YOUR ROLE:\n"
        "- ChatGPT = Orchestrator / Architect (High-level system design, decomposing features, reviewing code diffs).\n"
        "- Antigravity = Implementation Agent (Autonomous coding, terminal commands, refactoring, writing files).\n\n"
        "WORKFLOW:\n"
        "1. When the user asks to build or fix a feature, first call `listProjects` or `inspectProjectContext` to understand the codebase.\n"
        "2. Break down the user's request into actionable development prompts.\n"
        "3. Dispatch tasks using `createTask`.\n"
        "4. Poll task state using `getTaskStatus` until status is 'completed'.\n"
        "5. Review Antigravity's output and summarize changes to the user.\n"
        "6. If follow-up changes are needed, call `continueSession` on the previous task ID to preserve the conversational context."
    )
    return {"instructions": instructions}
