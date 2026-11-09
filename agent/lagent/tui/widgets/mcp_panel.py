"""MCP 侧边栏：展示 MCP 服务器连接状态与可用的工具列表。"""

from __future__ import annotations

from typing import Any, Dict, List

from textual.widgets import RichLog

__all__ = ["MCPPanel"]


_STATE_LABELS = {
    "pending": "待连接",
    "connecting": "连接中…",
    "connected": "已连接",
    "failed": "连接失败",
}


class MCPPanel(RichLog):
    """侧边栏面板：异步轮询 engine.mcp_status() 动态刷新。"""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("wrap", True)
        kwargs.setdefault("markup", False)
        kwargs.setdefault("highlight", False)
        kwargs.setdefault("auto_scroll", False)
        super().__init__(**kwargs)
        self._header_written = False

    def refresh_status(self, status: Dict[str, Any]) -> None:
        """根据引擎的 MCP 状态摘要刷新显示。"""
        lines: List[str] = []
        if not status.get("configured"):
            lines.append("── MCP 服务器 ──")
            lines.append("  未配置 .mcp.json")
            lines.append("  未发现 MCP 工具")
        else:
            lines.append(f"── MCP 服务器 ──{'（加载中…）' if status.get('loading') else ''}")
            servers: List[Dict[str, Any]] = status.get("servers") or []
            if not servers:
                lines.append("  无")
            for server in servers:
                name = server.get("server_name") or "?"
                state = server.get("state") or "pending"
                label = _STATE_LABELS.get(state, state)
                tools: List[str] = server.get("tools") or []
                lines.append(f"● {name}  [{label}]  {len(tools)} 工具")
                if state == "failed":
                    err = server.get("error") or "未知错误"
                    lines.append(f"    ✗ {err[:60]}")
                elif state == "connected":
                    for tool in tools[:30]:
                        lines.append(f"    · {tool}")
                    if len(tools) > 30:
                        lines.append(f"    … 其余 {len(tools) - 30} 个未列出")
        self.clear()
        self.write("\n".join(lines) if lines else "── MCP 服务器 ──\n  无")