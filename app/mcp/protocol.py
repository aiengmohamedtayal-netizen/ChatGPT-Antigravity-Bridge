"""Model Context Protocol (MCP) 2024-11-05 JSON-RPC specification models."""

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

JSONRPC_VERSION = "2.0"
MCP_PROTOCOL_VERSION = "2024-11-05"


class JsonRpcRequest(BaseModel):
    jsonrpc: str = JSONRPC_VERSION
    id: Optional[Union[str, int]] = None
    method: str
    params: Optional[Dict[str, Any]] = Field(default_factory=dict)


class JsonRpcError(BaseModel):
    code: int
    message: str
    data: Optional[Any] = None


class JsonRpcResponse(BaseModel):
    jsonrpc: str = JSONRPC_VERSION
    id: Optional[Union[str, int]] = None
    result: Optional[Any] = None
    error: Optional[JsonRpcError] = None


class McpToolInputSchema(BaseModel):
    type: str = "object"
    properties: Dict[str, Any] = Field(default_factory=dict)
    required: Optional[List[str]] = Field(default_factory=list)


class McpTool(BaseModel):
    name: str
    description: str
    inputSchema: McpToolInputSchema


class McpContentItem(BaseModel):
    type: str = "text"
    text: str


class McpToolResult(BaseModel):
    content: List[McpContentItem]
    isError: bool = False
