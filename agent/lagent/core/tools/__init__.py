"""工具集合：把内置工具组装成默认注册表。"""

from __future__ import annotations

from .base import ToolError, ToolRegistry, ToolSpec
from .file_tools import FILE_TOOLS
from .system_tools import SYSTEM_TOOLS

__all__ = ["ToolError", "ToolRegistry", "ToolSpec", "build_registry"]


def build_registry() -> ToolRegistry:
    """构建默认工具注册表（系统工具 + 文件工具）。"""
    registry = ToolRegistry()
    registry.register_many(SYSTEM_TOOLS)
    registry.register_many(FILE_TOOLS)
    return registry
