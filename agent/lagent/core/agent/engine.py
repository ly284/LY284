"""Agent 引擎：编排“提问 → 流式回答 → 工具调用 → 继续回答”的主循环。

引擎与任何界面无关：`ask()` 是一个同步生成器，逐步产出 core.events
中的事件；TUI / Web / Desktop 只需消费这些事件即可，无需了解内部实现。
"""

from __future__ import annotations

import os
import threading
from datetime import datetime
from typing import Any, Dict, Generator, Iterator, List, Optional, Tuple

from ..context import (
    COMPRESSION_SYSTEM_PROMPT,
    DEFAULT_COMPRESS_MAX_TOKENS,
    DEFAULT_CONTEXT_WINDOW,
    ContextArchiver,
    estimate_usage,
    format_transcript,
)
from ..events import (
    AnswerDelta,
    ContextCompressionFailed,
    ContextCompressionFinished,
    ContextCompressionSkipped,
    ContextCompressionStarted,
    ContextUsage,
    ContextWarning,
    ErrorEvent,
    Event,
    SessionCleared,
    ToolCallFinished,
    ToolCallStarted,
    TurnFinished,
    TurnLimited,
)
from ..llm.client import LLMClient
from ..llm.thinking import ThinkFilter, strip_think
from ..mcp import MCPClientManager, register_connected_server
from ..session import Conversation
from ..session_store import SessionInfo, SessionStore
from ..tools import ToolRegistry

__all__ = ["AgentEngine", "TurnCancelled"]

DEFAULT_MAX_ROUNDS = 5

# 项目工作指引文件名：默认兼容 AGENTS.md / AGENT.md 两种等价命名，
# 可通过 agents_file 参数显式指定（config.ini 的 [agent] agents_file）。
DEFAULT_AGENTS_FILES = ("AGENTS.md", "AGENT.md")
# AGENTS.md 指引消息的识别标记（写在内容开头）
AGENTS_MARKER = "[AGENTS.md 项目工作指引]"
# 指引内容注入长度上限：超出截断，避免一次性占满上下文
MAX_AGENTS_CONTENT_CHARS = 8_000


class TurnCancelled(Exception):
    """本轮执行被用户中断（界面收到后应回到空闲态，而非当作错误）。"""


class AgentEngine:
    """与界面无关的 Agent 运行引擎。"""

    def __init__(
        self,
        client: LLMClient,
        registry: ToolRegistry,
        conversation: Optional[Conversation] = None,
        max_rounds: int = DEFAULT_MAX_ROUNDS,
        mcp_manager: Optional[MCPClientManager] = None,
        *,
        context_window: Optional[int] = None,
        compress_threshold: float = 0.6,
        archiver: Optional[ContextArchiver] = None,
        sessions_dir: str = ".agents/sessions",
        agents_file: str = "",
    ) -> None:
        self._client = client
        self._registry = registry
        self._conversation = conversation or Conversation()
        self._max_rounds = max(1, int(max_rounds))
        self._mcp_manager = mcp_manager
        self._archiver = archiver or ContextArchiver()
        self._session_store = SessionStore(sessions_dir)
        self._mcp_loading_thread: Optional[threading.Thread] = None
        self._closed = False
        # 指引文件名：显式指定则只查这一个，否则按 AGENTS.md / AGENT.md 顺序兼容查找
        self._agents_files = (agents_file.strip(),) if agents_file.strip() else DEFAULT_AGENTS_FILES

        # 上下文窗口：显式配置 > 尝试查询模型服务 > 默认 128k（标记「默认」）
        if context_window and context_window > 0:
            self._context_window = int(context_window)
            self._window_default = False
        else:
            fetched = client.fetch_context_window()
            if fetched and fetched > 0:
                self._context_window = int(fetched)
                self._window_default = False
            else:
                self._context_window = DEFAULT_CONTEXT_WINDOW
                self._window_default = True
        self._compress_threshold = min(1.0, max(0.01, float(compress_threshold)))
        self._context_locked = False

        # 记录初始 System Prompt，供 reset / 恢复会话后复原
        self._base_system_prompt = ""
        if self._conversation.messages and self._conversation.messages[0].get("role") == "system":
            self._base_system_prompt = self._conversation.messages[0].get("content") or ""

        # AGENTS.md：一次注入，全程复用 —— 首次加载时作为一条消息追加到聊天历史
        self._agents_message: Optional[Dict[str, Any]] = None
        agents_content = self._read_agents_content(os.getcwd())
        if agents_content:
            self._agents_message = {"role": "user", "content": agents_content}
            self._conversation.insert_after_system(self._agents_message)

    # ---------- 资源清理 ----------

    def close(self) -> None:
        """释放持有资源的连接（如 MCP 服务器后台线程）。"""
        self._closed = True
        if self._mcp_manager is not None:
            self._mcp_manager.close()
            self._mcp_manager = None

    # ---------- 只读属性 ----------

    @property
    def client(self) -> LLMClient:
        return self._client

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    @property
    def conversation(self) -> Conversation:
        return self._conversation

    @property
    def max_rounds(self) -> int:
        return self._max_rounds

    @property
    def model(self) -> str:
        return self._client.model

    @property
    def archiver(self) -> ContextArchiver:
        return self._archiver

    @property
    def context_locked(self) -> bool:
        """上下文占用达到阈值后，是否暂停接受普通提问。"""
        return self._context_locked

    def context_usage(self) -> Dict[str, Any]:
        """计算当前上下文占用情况（供界面展示与阈值判断）。

        - 优先使用模型 API 返回的真实 Token 使用量；
        - 拿不到时按消息内容做粗略估算。
        """
        used = estimate_usage(
            self._conversation.messages,
            tool_defs=self._registry.openai_tools(),
        )
        if self._client.last_usage and self._client.last_usage > 0:
            used = self._client.last_usage
        percent = used / self._context_window
        return {
            "used": used,
            "window": self._context_window,
            "percent": percent,
            "window_default": self._window_default,
            "threshold": self._compress_threshold,
            "locked": self._context_locked,
        }

    # ---------- 会话控制 ----------
    def reset(self) -> SessionCleared:
        """清空对话历史（保留 System Prompt 与 AGENTS.md 指引），解除输入限制。"""
        self._conversation.clear()
        if self._base_system_prompt:
            self._conversation.add({"role": "system", "content": self._base_system_prompt})
        if self._agents_message is not None:
            self._conversation.insert_after_system(self._agents_message)
        self._context_locked = False
        self._client._last_usage = None  # noqa: SLF001 - 清空失效的真实用量
        return SessionCleared()

    # ---------- 会话保存 / 恢复（/new /save /resume） ----------

    @property
    def session_store(self) -> SessionStore:
        return self._session_store

    def save_session(self) -> Optional[SessionInfo]:
        """保存当前会话历史到 `.agents/sessions/`，返回摘要；无可保存内容时返回 None。"""
        messages = [m for m in self._conversation.messages if not self._is_agents_message(m)]
        if not any(m.get("role") in ("user", "assistant", "tool") for m in messages):
            return None
        return self._session_store.save(messages)

    def list_sessions(self, limit: int = 50) -> List[SessionInfo]:
        """列出最近保存的会话。"""
        return self._session_store.list_sessions(limit)

    def resume_session(self, session_id: str) -> Optional[List[Dict[str, Any]]]:
        """恢复指定会话：整体替换聊天历史，并重新注入 AGENTS.md 指引。"""
        messages = self._session_store.load(session_id)
        if messages is None:
            return None
        self._conversation.replace_all(messages)
        self._sync_base_from_conversation()
        self._ensure_agents_injected()
        self._context_locked = False
        self._client._last_usage = None  # noqa: SLF001 - 恢复后用量以估算为准
        return messages

    def _sync_base_from_conversation(self) -> None:
        if self._conversation.messages and self._conversation.messages[0].get("role") == "system":
            self._base_system_prompt = self._conversation.messages[0].get("content") or ""

    def _ensure_agents_injected(self) -> None:
        if self._agents_message is not None:
            return
        content = self._read_agents_content(os.getcwd())
        if content:
            self._agents_message = {"role": "user", "content": content}
            self._conversation.insert_after_system(self._agents_message)

    # ---------- MCP 异步加载 ----------

    def start_mcp_loading(self) -> None:
        """后台线程异步连接 MCP 服务器（先进入界面，加载完动态刷新侧边栏）。"""
        if self._mcp_manager is None or self._closed:
            return
        if self._mcp_loading_thread is not None and self._mcp_loading_thread.is_alive():
            return
        self._mcp_manager.mark_loading()
        self._mcp_loading_thread = threading.Thread(
            target=self._load_mcp_in_background,
            name="mcp-loader",
            daemon=True,
        )
        self._mcp_loading_thread.start()

    def _load_mcp_in_background(self) -> None:
        try:
            for server_name in self._mcp_manager.server_names:
                if self._closed:
                    break
                worker = self._mcp_manager.connect_server(server_name)
                if worker is None:
                    continue
                register_connected_server(self._registry, worker)
        finally:
            if self._mcp_manager is not None:
                self._mcp_manager.mark_loading_done()
    def mcp_status(self) -> Dict[str, Any]:
        """MCP 服务器连接状态（供界面侧边栏轮询刷新）。"""
        if self._mcp_manager is None:
            return {"configured": False, "loading": False, "servers": []}
        return {
            "configured": True,
            "loading": self._mcp_manager.loading,
            "servers": self._mcp_manager.status_summary(),
        }

    # ---------- AGENTS.md ----------

    def _read_agents_content(self, project_root: str) -> str:
        """读取项目根目录下的工作指引（AGENTS.md / AGENT.md 或自定义命名）。

        不存在或读取失败时返回空串；超长内容截断到 MAX_AGENTS_CONTENT_CHARS。
        """
        for name in self._agents_files:
            path = os.path.join(project_root, name)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    content = fh.read().strip()
            except (OSError, UnicodeDecodeError):
                continue
            if not content:
                continue
            if len(content) > MAX_AGENTS_CONTENT_CHARS:
                content = (
                    content[:MAX_AGENTS_CONTENT_CHARS]
                    + f"\n\n[指引过长，已截断，原文共 {len(content)} 字符，"
                    f"仅注入前 {MAX_AGENTS_CONTENT_CHARS} 字符]"
                )
            return f"{AGENTS_MARKER}\n{content}"
        return ""

    @staticmethod
    def _is_agents_message(message: Dict[str, Any]) -> bool:
        content = message.get("content") or ""
        return isinstance(content, str) and content.startswith(AGENTS_MARKER)

    def ask(
        self,
        question: str,
        cancel_event: Optional[threading.Event] = None,
    ) -> Iterator[Event]:
        """提出一个问题，逐步产出本轮事件。

        事件序列：AnswerDelta* （流式回答），其间穿插
        ToolCallStarted/ToolCallFinished，最后以 TurnFinished、
        TurnLimited 或 ErrorEvent 结束。失败时会话历史自动回滚。

        上下文监控：每轮正常结束后追加产出 ContextUsage，并在占用达到
        阈值时追加 ContextWarning 且锁定输入（须先执行 /compact）。

        Args:
            cancel_event: 可选的取消信号；被置位时本轮在安全的
                边界（每块流式增量、每次工具调用前）抛出 TurnCancelled，
                调用方应据此回到空闲态而不是当作错误。
        """
        question = (question or "").strip()
        if not question:
            return
        if self._context_locked:
            yield ErrorEvent(
                message=(
                    f"上下文占用已达到 {int(self._compress_threshold * 100)}% 阈值，"
                    "请先执行 /compact 完成上下文压缩后再继续提问"
                )
            )
            return

        mark = self._conversation.mark()
        self._conversation.add_user(question)
        try:
            for event in self._run_turn(cancel_event):
                yield event
        except TurnCancelled:
            self._conversation.rollback(mark)
            raise
        except Exception as exc:  # noqa: BLE001 - 网络/SDK 异常统一转事件
            self._conversation.rollback(mark)
            yield ErrorEvent(
                message="与模型服务通信失败，请检查服务是否已启动、网络与配置",
                detail=f"{type(exc).__name__}: {exc}",
            )
            return

        # 本轮正常结束时检查上下文占用
        usage = self.context_usage()
        yield ContextUsage(
            used=usage["used"],
            window=usage["window"],
            percent=usage["percent"],
            window_default=usage["window_default"],
            locked=self._context_locked,
        )
        if usage["percent"] >= self._compress_threshold:
            self._context_locked = True
            yield ContextWarning(
                used=usage["used"],
                window=usage["window"],
                percent=usage["percent"],
            )

    # ---------- 上下文压缩 ----------

    def compact(
        self,
        cancel_event: Optional[threading.Event] = None,
    ) -> Iterator[Event]:
        """执行上下文压缩：归档原始上下文 → LLM 生成摘要 → 替换会话历史。

        压缩期间不运行 ask()，也不执行任何 Function Calling 工具。
        压缩成功后解除输入限制；失败时会话历史保持不变。

        事件序列：ContextCompressionStarted → ContextCompressionFinished，
        失败时产出 ContextCompressionFailed；历史过短时产出
        ContextCompressionSkipped。
        """
        if cancel_event is not None and cancel_event.is_set():
            raise TurnCancelled()

        messages = self._conversation.messages
        history = [m for m in messages if m.get("role") != "system"]
        if len(history) < 2:
            yield ContextCompressionSkipped(
                reason="对话历史过短，暂不需要压缩（至少需要一问一答）"
            )
            return

        # 1) 先保存完整原始上下文，成功后才能继续
        archive_id = self._archiver.new_id()
        try:
            self._archiver.save(messages, archive_id)
        except Exception as exc:  # noqa: BLE001 - 归档失败直接中止压缩
            yield ContextCompressionFailed(
                message="原始上下文归档保存失败，已中止压缩",
                detail=f"{type(exc).__name__}: {exc}",
            )
            return

        yield ContextCompressionStarted(archive_id=archive_id)

        # 2) 调用 LLM 生成工作摘要（专用压缩 Prompt）
        if cancel_event is not None and cancel_event.is_set():
            raise TurnCancelled()
        original_transcript = format_transcript(messages)
        try:
            summary = self._client.complete(
                messages=[
                    {"role": "system", "content": COMPRESSION_SYSTEM_PROMPT},
                    {"role": "user", "content": original_transcript},
                ],
                max_tokens=DEFAULT_COMPRESS_MAX_TOKENS,
                temperature=0.3,
            )
        except Exception as exc:  # noqa: BLE001 - 网络/SDK 异常统一转失败事件
            yield ContextCompressionFailed(
                message="调用模型生成上下文摘要失败",
                detail=f"{type(exc).__name__}: {exc}",
            )
            return

        summary = strip_think(summary).strip()
        if not summary:
            yield ContextCompressionFailed(
                message="调用模型生成上下文摘要失败",
                detail="模型返回内容为空",
            )
            return

        if cancel_event is not None and cancel_event.is_set():
            raise TurnCancelled()

        # 3) 末尾追加归档说明
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        note = (
            f"\n\n> 此前上下文已于 {timestamp} 完成压缩，原始上下文保存在编号为 "
            f"{archive_id} 的归档文件中。如需查找历史信息，请使用 recallContext 工具。"
        )
        full_summary = summary.rstrip() + note

        # 4) 用摘要替换会话历史（保留 System Prompt 与工具定义）
        self._conversation.replace_with_summary(full_summary)
        self._context_locked = False
        self._client._last_usage = None  # noqa: SLF001 - 摘要后的用量以估算为准

        used_after = estimate_usage(
            self._conversation.messages,
            tool_defs=self._registry.openai_tools(),
        )
        yield ContextCompressionFinished(
            archive_id=archive_id,
            summary=full_summary,
            original=original_transcript,
            used_after=used_after,
        )

    # ---------- 内部实现 ----------

    def _run_turn(
        self,
        cancel_event: Optional[threading.Event] = None,
    ) -> Generator[Event, None, None]:
        rounds = 0
        while rounds < self._max_rounds:
            if cancel_event is not None and cancel_event.is_set():
                raise TurnCancelled()
            rounds += 1
            printed, calls = yield from self._stream_round(cancel_event)

            if not calls:
                # 没有工具调用，本轮回答结束
                self._conversation.add_assistant(printed)
                yield TurnFinished(text=printed, rounds=rounds)
                return

            # 把工具调用记入历史，再把执行结果交给模型继续回答
            self._conversation.add_assistant(printed or None, tool_calls=calls)
            for call in calls:
                if cancel_event is not None and cancel_event.is_set():
                    raise TurnCancelled()
                fn = call["function"]
                name = fn.get("name") or ""
                arguments = fn.get("arguments") or "{}"
                yield ToolCallStarted(name=name, arguments=arguments)
                result = self._registry.execute(name, arguments, cancel_event=cancel_event)
                yield ToolCallFinished(name=name, result=result)
                self._conversation.add_tool_result(call["id"], result)

        yield TurnLimited(rounds=self._max_rounds)

    def _stream_round(
        self,
        cancel_event: Optional[threading.Event] = None,
    ) -> Generator[Event, None, Tuple[str, List[Dict[str, Any]]]]:
        """请求一轮流式回答，产出增量事件，返回 (可见文本, 工具调用列表)。"""
        flt = ThinkFilter()
        printed = ""
        pending: Dict[int, Dict[str, str]] = {}

        stream = self._client.stream(
            self._conversation.messages, tools=self._registry.openai_tools()
        )
        for chunk in stream:
            if cancel_event is not None and cancel_event.is_set():
                raise TurnCancelled()
            for tc in chunk.tool_calls:
                slot = pending.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                if tc.id:
                    slot["id"] = tc.id
                if tc.name:
                    slot["name"] = tc.name
                if tc.arguments:
                    slot["arguments"] += tc.arguments

            if not chunk.text:
                continue
            delta, replace = flt.feed(chunk.text)
            if delta or replace:
                printed = flt.visible
                yield AnswerDelta(text=delta, replace=replace)

        calls = [
            {
                "id": pending[i]["id"] or f"call_{i}",
                "type": "function",
                "function": {
                    "name": pending[i]["name"],
                    "arguments": pending[i]["arguments"] or "{}",
                },
            }
            for i in sorted(pending)
        ]
        return printed, calls
