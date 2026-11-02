"""工具集合：把内置工具组装成默认注册表。"""

from __future__ import annotations

from typing import Optional

from .base import ToolError, ToolRegistry, ToolSpec
from .file_tools import FILE_TOOLS
from .system_tools import SYSTEM_TOOLS
from .web_search import DEFAULT_ENDPOINT, build_search_tool

__all__ = ["ToolError", "ToolRegistry", "ToolSpec", "build_registry"]


def build_registry(
    *,
    search_api_key: Optional[str] = None,
    search_endpoint: str = DEFAULT_ENDPOINT,
    search_timeout: float = 30.0,
) -> ToolRegistry:
    """构建默认工具注册表（系统工具 + 文件工具 + 网络搜索）。

    传入 [search] 段的配置即可为 LLM 提供 searchWeb 联网搜索能力；
    未传 api_key 时也能正常构建，searchWeb 会在执行时提示配置缺失。
    """
    registry = ToolRegistry()
    registry.register_many(SYSTEM_TOOLS)
    registry.register_many(FILE_TOOLS)
    registry.register(
        build_search_tool(
            search_api_key or "",
            endpoint=search_endpoint,
            timeout=search_timeout,
        )
    )
    return registry
