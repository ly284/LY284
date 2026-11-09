"""MCP 客户端与工具注册。

设计要点：
- 每个 MCP 服务器在独立的守护线程里运行自己的 asyncio 事件循环，
  在该循环内建立并长期保持 MCP 会话（stdio 或 streamable_http）。
- 同步侧（lagent 的 ToolSpec.handler）通过
  ``asyncio.run_coroutine_threadsafe`` 把调用投递到服务器线程；
  对单个服务器的调用天然串行，避免同一会话并发冲突。
- 已连接失败 / 被关停的服务器只影响自身调用，抛出的错误会以文本
  形式回传给模型，不影响其它 MCP 或本地工具。
"""

from __future__ import annotations

import asyncio
import sys
import threading
from typing import Any, Dict, List, Optional

from ..tools import ToolError, ToolRegistry, ToolSpec
from .config import (
    DEFAULT_TOOL_TIMEOUT,
    MCPServerConfig,
)

__all__ = [
    "MCPClientManager",
    "MCPStatusError",
    "build_mcp_registry",
    "register_connected_server",
]

# LLM 暴露给工具名的前缀与原始工具名之间的分隔符。
# 例如服务器 “Bazi-MCP” 的 “get_bazi” -> “Bazi-MCP:get_bazi”；
# 用 “:” 便于模型辨认，也几乎不会与本地工具名冲突。
_NAME_SEP = ":"

# 内容块类型常量（来自 mcp.types，避免强依赖其枚举名）
_TEXT = "text"
_IMAGE = "image"
_RESOURCE = "resource"
_AUDIO = "audio"

# 连接状态取值（供 TUI 侧边栏展示）
STATE_PENDING = "pending"
STATE_CONNECTING = "connecting"
STATE_CONNECTED = "connected"
STATE_FAILED = "failed"


class MCPStatusError(Exception):
    """MCP 状态聚合异常（一般不会用到，保留扩展能力）。"""


def _sanitize_schema(schema: Any) -> Dict[str, Any]:
    """把 MCP 提供的 JSON Schema 规整成 OpenAI 兼容的参数声明。

    - 去掉 OpenAI 不认识的顶层 ``$schema`` / ``title`` 键；
    - 对 ``properties`` 递归处理（个别 MCP 服务器会在属性里也带 $ref / $schema）。
    """
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}
    out: Dict[str, Any] = {}
    for key, value in schema.items():
        if key in ("$schema", "title", "description"):
            if key == "description" and isinstance(value, str):
                out[key] = value
            continue
        if key == "properties" and isinstance(value, dict):
            out[key] = {
                pk: _sanitize_schema(pv)
                for pk, pv in value.items()
                if isinstance(pv, dict)
            }
        else:
            out[key] = value
    return out


def _format_mcp_result(result: Any) -> str:
    """把 MCP CallToolResult 的内容规范成文本交给模型。

    处理：文本块、图像/音频/嵌入资源块、结构化字典块（结构化输出）、
    以及 isError 标记。无法识别的块按 repr 兜底，保证永远能拿到文本。
    """
    blocks = getattr(result, "content", None) or []
    is_error = bool(getattr(result, "isError", False))

    parts: List[str] = []
    for block in blocks:
        if block is None:
            continue
        kind = getattr(block, "type", None)
        text = getattr(block, "text", None)
        if kind == _TEXT and isinstance(text, str):
            parts.append(text)
        elif isinstance(block, dict):
            # 结构化数据块（新版本 SDK 返回 dict，无 .text 属性）
            btype = block.get("type")
            btext = block.get("text")
            if btype == _TEXT and isinstance(btext, str):
                parts.append(btext)
            else:
                try:
                    import json as _json

                    parts.append(_json.dumps(block, ensure_ascii=False))
                except Exception:  # noqa: BLE001
                    parts.append(repr(block))
        elif kind == _IMAGE:
            img = {
                "type": "image",
                "mimeType": getattr(block, "mimeType", "unknown"),
                "dataB64": (getattr(block, "data", None) or "")[:80],
            }
            parts.append(f"[图像内容 已省略二进制数据] {img}")
        elif kind == _RESOURCE:
            parts.append(f"[资源内容] {getattr(block, 'uri', '')} {repr(block)}")
        elif kind == _AUDIO:
            parts.append("[音频内容 已省略二进制数据]")
        else:
            parts.append(repr(block))

    text_out = "\n".join(p for p in parts if p)
    if is_error:
        note = f"[MCP 工具返回错误: {getattr(result, 'message', '')}]".strip()
        return (note + "\n" + text_out).strip()
    return text_out or "（MCP 工具无返回内容）"


class _ServerWorker:
    """单个 MCP 服务器的异步工作线程与同步调用桥。"""

    # 线程内退出运输层会话的最长等待，避免网络 keep-alive 阻塞关停
    _CLOSE_TIMEOUT = 3.0

    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._transport_ctx: Optional[Any] = None
        self._session: Optional[Any] = None
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._ready = threading.Event()
        self._connect_error: Optional[Exception] = None
        self._closed = False
        self._shutdown_lock = threading.Lock()

    # ---------- 生命周期 ----------

    def connect(self) -> None:
        """启动线程并等待握手完成；失败时把错误保存并通过异常抛出。"""
        self._thread = threading.Thread(
            target=self._run_loop,
            name=f"mcp-{self.config.name}-client",
            daemon=True,
        )
        self._thread.start()
        self._ready.wait(timeout=self.config.connect_timeout)
        if self._connect_error is not None:
            raise self._connect_error

    def close(self) -> None:
        with self._shutdown_lock:
            if self._closed:
                return
            self._closed = True
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

    @property
    def alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and self._session is not None

    # ---------- 生命周期：线程主入口 ----------

    def _run_loop(self) -> None:
        """服务器线程主入口：建立会话后进入 run_forever。

        注意：握手阶段可能抛 ``asyncio.CancelledError``（属 BaseException 而非
        Exception，例如远程服务器不可达时 streamable_http 在 initialize 阶段以
        cancel scope 方式报错），因此这里必须用 ``BaseException`` 捕获并上报，
        否则连接失败会绕过异常处理、留下脏线程。
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._setup_session())
        except BaseException as exc:  # noqa: BLE001 - 连接失败要上报给同步侧
            self._connect_error = exc
            self._ready.set()
            try:
                loop.run_until_complete(self._aexit_session())
            except Exception:  # noqa: BLE001
                pass
            try:
                loop.close()
            except Exception:  # noqa: BLE001
                pass
            self._loop = None
            return
        self._ready.set()
        # 此后事件循环常驻，接收同步侧投递的调用
        try:
            loop.run_forever()
        finally:
            # 退出时清理运输层与会话（带超时，避免网络 keep-alive 阻塞关停）
            try:
                if self._session is not None or self._transport_ctx is not None:
                    loop.run_until_complete(
                        asyncio.wait_for(self._aexit_session(), timeout=self._CLOSE_TIMEOUT)
                    )
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:  # noqa: BLE001
                pass
            finally:
                loop.close()
                self._loop = None

    # ---------- 会话建立 ----------

    async def _setup_session(self) -> None:
        from mcp import ClientSession

        if self.config.is_stdio:
            from mcp import StdioServerParameters
            from mcp.client.stdio import stdio_client

            params = StdioServerParameters(
                command=self.config.command,
                args=self.config.args,
                env=self.config.env or None,
                cwd=self.config.cwd,
            )
            transport_ctx = stdio_client(params)
        else:
            from mcp.client.streamable_http import streamable_http_client

            transport_ctx = streamable_http_client(url=self.config.url)
        self._transport_ctx = transport_ctx
        read_stream, write_stream = await transport_ctx.__aenter__()
        session = ClientSession(read_stream, write_stream)
        await session.__aenter__()
        await session.initialize()
        self._session = session

        # 拉取工具清单
        result = await session.list_tools()
        self._tools = {}
        for tool in result.tools:
            schema = getattr(tool, "input_schema", None) or getattr(
                tool, "inputSchema", None
            ) or {}
            self._tools[tool.name] = {
                "name": tool.name,
                "description": tool.description or "",
                "inputSchema": _sanitize_schema(schema),
            }

    async def _aexit_session(self) -> None:
        if self._session is not None:
            try:
                await self._session.__aexit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass
            self._session = None
        if self._transport_ctx is not None:
            try:
                await self._transport_ctx.__aexit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass
            self._transport_ctx = None

    # ---------- 同步调用桥 ----------

    @property
    def tools(self) -> Dict[str, Dict[str, Any]]:
        return self._tools

    async def _call_tool_async(self, name: str, arguments: Dict[str, Any]) -> Any:
        if self._session is None:
            raise RuntimeError("MCP 会话未建立")
        return await self._session.call_tool(name, arguments)

    def call_tool_sync(
        self, name: str, arguments: Dict[str, Any], timeout: Optional[float] = None
    ) -> str:
        """同步执行一次 MCP 工具调用并返回交给模型的文本。"""
        if not self.alive or self._loop is None or self._session is None:
            raise RuntimeError(f"MCP 服务器 '{self.config.name}' 未连接，无法调用工具")
        wait = timeout or self.config.tool_timeout or DEFAULT_TOOL_TIMEOUT
        fut = asyncio.run_coroutine_threadsafe(
            self._call_tool_async(name, arguments), self._loop
        )
        try:
            result = fut.result(timeout=wait)
        except asyncio.TimeoutError as exc:
            raise ToolError(
                f"MCP 服务器 '{self.config.name}' 调用工具 '{name}' 超时 "
                f"({wait}s)"
            ) from exc
        except Exception as exc:  # noqa: BLE001 - 交给模型判断
            raise ToolError(
                f"MCP 服务器 '{self.config.name}' 调用工具 '{name}' 失败: {exc}"
            ) from exc
        return _format_mcp_result(result)


class MCPClientManager:
    """聚合管理所有 MCP 服务器客户端。

    支持后台异步加载：调用 `mark_loading()` 后由引擎在独立线程中
    逐个连接服务器并注册工具，界面通过 `status_summary()` 轮询刷新。
    """

    def __init__(self, servers: Optional[Dict[str, MCPServerConfig]] = None) -> None:
        servers = servers or {}
        self._servers: Dict[str, MCPServerConfig] = dict(servers)
        self._workers: Dict[str, _ServerWorker] = {}
        self._state: Dict[str, str] = {name: STATE_PENDING for name in self._servers}
        self._errors: Dict[str, str] = {}
        self._loading = False
        self._lock = threading.Lock()

    @property
    def server_names(self) -> List[str]:
        return list(self._servers)

    def has_server(self, name: str) -> bool:
        with self._lock:
            return name in self._workers

    def _set_state(self, name: str, state: str, error: Optional[str] = None) -> None:
        with self._lock:
            self._state[name] = state
            if error:
                self._errors[name] = error
            else:
                self._errors.pop(name, None)

    def mark_loading(self) -> None:
        with self._lock:
            self._loading = True

    def mark_loading_done(self) -> None:
        with self._lock:
            self._loading = False

    @property
    def loading(self) -> bool:
        with self._lock:
            return self._loading

    def connect_server(self, name: str) -> Optional[_ServerWorker]:
        """连接（或复用）某个 MCP 服务器，失败时返回 None 并记录状态。"""
        with self._lock:
            existing = self._workers.get(name)
        if existing is not None:
            return existing
        config = self._servers.get(name)
        if config is None:
            self._set_state(name, STATE_FAILED, "未配置服务器")
            print(f"[MCP] 未配置服务器: {name}", file=sys.stderr)
            return None
        self._set_state(name, STATE_CONNECTING, None)
        worker = _ServerWorker(config)
        try:
            worker.connect()
        except BaseException as exc:  # noqa: BLE001 - 单服务器失败不影响其它工具
            # 注意用 BaseException：不可达服务器常以 CancelledError（BaseException）
            # 方式在握手阶段报错，普通 Exception 抓不到会导致整个启动崩溃。
            self._set_state(name, STATE_FAILED, f"{type(exc).__name__}: {exc}")
            print(
                f"[MCP] 服务器 '{name}' 连接失败，已跳过该服务器的工具: {exc}",
                file=sys.stderr,
            )
            return None
        with self._lock:
            self._workers[name] = worker
        self._set_state(name, STATE_CONNECTED, None)
        count = len(worker.tools)
        print(
            f"[MCP] 服务器 '{name}' 已连接，发现并注册 {count} 个工具",
            file=sys.stderr,
        )
        return worker

    def status_summary(self) -> List[Dict[str, Any]]:
        """供界面展示的每台服务器状态摘要。"""
        with self._lock:
            states = dict(self._state)
            errors = dict(self._errors)
            workers = dict(self._workers)
        out: List[Dict[str, Any]] = []
        for name in self._servers:
            worker = workers.get(name)
            tool_names: List[str] = []
            if worker is not None:
                tool_names = [f"{name}{_NAME_SEP}{tool}" for tool in worker.tools.keys()]
            out.append(
                {
                    "server_name": name,
                    "state": states.get(name, STATE_PENDING),
                    "error": errors.get(name),
                    "tools": tool_names,
                }
            )
        return out

    def close(self) -> None:
        with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()
            self._loading = False
        for worker in workers:
            worker.close()
        self._state = {name: STATE_PENDING for name in self._servers}
        self._errors.clear()


def _build_spec(exposed_name: str, server_name: str, tool: Dict[str, Any], worker: _ServerWorker) -> ToolSpec:
    def handler(**kwargs: Any) -> str:
        return worker.call_tool_sync(tool["name"], kwargs)

    return ToolSpec(
        name=exposed_name,
        description=(
            f"（外部 MCP 服务器 '{server_name}' 提供的工具）"
            f"{tool['description']}"
        ),
        parameters=tool["inputSchema"] or {"type": "object", "properties": {}},
        handler=handler,
    )


def register_connected_server(registry: ToolRegistry, worker: _ServerWorker) -> int:
    """把已连接服务器的全部工具注册到 registry，返回注册数量。"""
    registered = 0
    for tool_name, tool in worker.tools.items():
        exposed = f"{worker.config.name}{_NAME_SEP}{tool_name}"
        try:
            registry.register(_build_spec(exposed, worker.config.name, tool, worker))
        except ValueError:
            print(
                f"[MCP] 工具名冲突，跳过 '{exposed}'（已有同名工具被注册）",
                file=sys.stderr,
            )
            continue
        registered += 1
    return registered


def build_mcp_registry(
    registry: ToolRegistry,
    servers: Optional[Dict[str, MCPServerConfig]] = None,
    manager: Optional[MCPClientManager] = None,
) -> ToolRegistry:
    """把 `.mcp.json` 中的每个服务器工具注册到现成 registry 里。

    同步版本：逐个连接服务器并注册。界面启动时建议改用引擎提供的
    后台加载（先进入界面，连接完成后动态刷新侧边栏）。

    返回同一个 registry，便于链式调用。工具名以 ``服务器名:工具名`` 暴露，
    避免不同服务器工具重名；执行时据此映射回对应服务器。
    """
    mgr = manager or MCPClientManager(servers)
    mgr.mark_loading()
    connected = 0
    for server_name in mgr.server_names:
        worker = mgr.connect_server(server_name)
        if worker is None:
            continue
        connected += 1
        register_connected_server(registry, worker)
    mgr.mark_loading_done()
    if connected == 0 and mgr.server_names:
        print("[MCP] 没有成功连接任何 MCP 服务器", file=sys.stderr)
    return registry
