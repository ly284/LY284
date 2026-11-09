"""MCP（Model Context Protocol）客户端支持。

连接 stdio / streamable_http 两类 MCP 服务器，把服务器提供的工具
动态注册进 lagent 的工具集合，让模型可按 Function Calling 的方式调用。
"""

from __future__ import annotations

from .client import (
    MCPClientManager,
    build_mcp_registry,
    register_connected_server,
)
from .config import (
    MCPServerConfig,
    MCPConfigError,
    load_mcp_servers,
)

__all__ = [
    "MCPClientManager",
    "MCPConfigError",
    "MCPServerConfig",
    "build_mcp_registry",
    "load_mcp_servers",
    "register_connected_server",
]
