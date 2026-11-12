"""MCP 服务器配置加载：从 `.mcp.json` 读取外部 MCP 服务器清单。

文件格式（兼容 Claude Desktop / 通用 MCP 客户端惯例）：

```json
{
  "mcpServers": {
    "weather": {
      "command": "uvx",
      "args": ["mcp-server-fetch"],
      "env": {"API_KEY": "..."},
      "cwd": "D:/tools"
    },
    "remote-search": {
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

- 带 `command` 的走本地进程管道（stdio）传输；
- 带 `url` 的走网络（Streamable HTTP）传输；
- 两者都没有、或 JSON 格式非法时抛出 MCPConfigError（上层会降级跳过 MCP，不阻塞主流程）。

查找顺序：显式 path 参数 > 环境变量 LAGENT_MCP_CONFIG > 当前目录 > 逐级向上查找父目录。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

__all__ = [
    "DEFAULT_TOOL_TIMEOUT",
    "DEFAULT_CONNECT_TIMEOUT",
    "MCPServerConfig",
    "MCPConfigError",
    "load_mcp_servers",
]

# 单次工具调用的默认超时（秒）；可在 .mcp.json 的 server 条目里用 "timeout" 覆盖
DEFAULT_TOOL_TIMEOUT = 60.0
# 建立 MCP 连接（握手）的超时（秒）
DEFAULT_CONNECT_TIMEOUT = 10.0

ENV_MCP_CONFIG = "LAGENT_MCP_CONFIG"
DEFAULT_MCP_FILE = ".mcp.json"


class MCPConfigError(Exception):
    """`.mcp.json` 缺失、格式非法或服务器条目不合法。"""


@dataclass(frozen=True)
class MCPServerConfig:
    """单台 MCP 服务器的连接配置。"""

    name: str
    url: str = ""
    command: str = ""
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    cwd: str = ""
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT
    tool_timeout: float = DEFAULT_TOOL_TIMEOUT

    @property
    def is_stdio(self) -> bool:
        """本地进程管道（stdio）传输：配置了 command 即视为 stdio。"""
        return bool(self.command)


def _find_config_file(path: Optional[str]) -> Path:
    if path:
        candidate = Path(path)
        if not candidate.is_file():
            raise MCPConfigError(f"未找到 MCP 配置文件: {candidate.absolute()}")
        return candidate

    env_path = os.environ.get(ENV_MCP_CONFIG, "").strip()
    if env_path:
        candidate = Path(env_path)
        if not candidate.is_file():
            raise MCPConfigError(f"环境变量 {ENV_MCP_CONFIG} 指向的配置不存在: {candidate.absolute()}")
        return candidate

    # 当前目录开始逐级向上查找 .mcp.json（便于在项目子目录里启动也能找到）
    current = Path.cwd()
    for directory in (current, *current.parents):
        candidate = directory / DEFAULT_MCP_FILE
        if candidate.is_file():
            return candidate
    raise MCPConfigError(
        f"未找到 {DEFAULT_MCP_FILE}（可在当前目录创建，或用环境变量 {ENV_MCP_CONFIG} 指定路径）"
    )


def _parse_server(name: str, entry: Any) -> MCPServerConfig:
    if not isinstance(entry, dict):
        raise MCPConfigError(f"MCP 服务器 '{name}' 的配置必须是对象")
    command = str(entry.get("command", "") or "").strip()
    url = str(entry.get("url", "") or "").strip()
    if not command and not url:
        raise MCPConfigError(f"MCP 服务器 '{name}' 缺少 command（stdio）或 url（HTTP）配置")

    args = entry.get("args") or []
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        raise MCPConfigError(f"MCP 服务器 '{name}' 的 args 必须是字符串数组")

    env = entry.get("env") or {}
    if not isinstance(env, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in env.items()
    ):
        raise MCPConfigError(f"MCP 服务器 '{name}' 的 env 必须是字符串键值对象")

    def _timeout(key: str, default: float) -> float:
        raw = entry.get(key, "")
        if raw in ("", None):
            return default
        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise MCPConfigError(f"MCP 服务器 '{name}' 的 {key} 必须是数值") from exc
        if value <= 0:
            raise MCPConfigError(f"MCP 服务器 '{name}' 的 {key} 必须 > 0")
        return value

    return MCPServerConfig(
        name=name,
        url=url,
        command=command,
        args=list(args),
        env=dict(env),
        cwd=str(entry.get("cwd", "") or ""),
        connect_timeout=_timeout("connect_timeout", DEFAULT_CONNECT_TIMEOUT),
        tool_timeout=_timeout("timeout", DEFAULT_TOOL_TIMEOUT),
    )


def load_mcp_servers(path: Optional[str] = None) -> Dict[str, MCPServerConfig]:
    """读取 `.mcp.json` 并解析成 name -> MCPServerConfig 字典；文件不存在时抛 MCPConfigError。"""
    config_path = _find_config_file(path)
    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise MCPConfigError(f"MCP 配置文件不是合法 JSON: {config_path.absolute()} ({exc})") from exc
    except OSError as exc:
        raise MCPConfigError(f"无法读取 MCP 配置文件: {config_path.absolute()} ({exc})") from exc

    servers_section = data.get("mcpServers")
    if not isinstance(servers_section, dict):
        raise MCPConfigError(f"MCP 配置缺少 mcpServers 对象: {config_path.absolute()}")

    servers: Dict[str, MCPServerConfig] = {}
    for name, entry in servers_section.items():
        if not isinstance(name, str) or not name.strip():
            raise MCPConfigError("MCP 服务器名必须是非空字符串")
        servers[name.strip()] = _parse_server(name.strip(), entry)
    return servers
