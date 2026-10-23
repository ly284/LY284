"""Agent 引擎：编排“提问 → 流式回答 → 工具调用 → 继续回答”的主循环。

引擎与任何界面无关：`ask()` 是一个同步生成器，逐步产出 core.events
中的事件；TUI / Web / Desktop 只需消费这些事件即可，无需了解内部实现。
"""

from __future__ import annotations

from typing import Any, Dict, Generator, Iterator, List, Optional, Tuple

from ..events import (
    AnswerDelta,
    ErrorEvent,
    Event,
    SessionCleared,
    ToolCallFinished,
    ToolCallStarted,
    TurnFinished,
    TurnLimited,
)
from ..llm.client import LLMClient
from ..llm.thinking import ThinkFilter
from ..session import Conversation
from ..tools import ToolRegistry

__all__ = ["AgentEngine"]

DEFAULT_MAX_ROUNDS = 5


class AgentEngine:
    """与界面无关的 Agent 运行引擎。"""

    def __init__(
        self,
        client: LLMClient,
        registry: ToolRegistry,
        conversation: Optional[Conversation] = None,
        max_rounds: int = DEFAULT_MAX_ROUNDS,
    ) -> None:
        self._client = client
        self._registry = registry
        self._conversation = conversation or Conversation()
        self._max_rounds = max(1, int(max_rounds))

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

    # ---------- 会话控制 ----------

    def reset(self) -> SessionCleared:
        """清空对话历史。"""
        self._conversation.clear()
        return SessionCleared()

    def ask(self, question: str) -> Iterator[Event]:
        """提出一个问题，逐步产出本轮事件。

        事件序列：AnswerDelta* （流式回答），其间穿插
        ToolCallStarted/ToolCallFinished，最后以 TurnFinished、
        TurnLimited 或 ErrorEvent 结束。失败时会话历史自动回滚。
        """
        question = (question or "").strip()
        if not question:
            return

        mark = self._conversation.mark()
        self._conversation.add_user(question)
        try:
            for event in self._run_turn():
                yield event
        except Exception as exc:  # noqa: BLE001 - 网络/SDK 异常统一转事件
            self._conversation.rollback(mark)
            yield ErrorEvent(
                message="与模型服务通信失败，请检查服务是否已启动、网络与配置",
                detail=f"{type(exc).__name__}: {exc}",
            )

    # ---------- 内部实现 ----------

    def _run_turn(self) -> Generator[Event, None, None]:
        rounds = 0
        while rounds < self._max_rounds:
            rounds += 1
            printed, calls = yield from self._stream_round()

            if not calls:
                # 没有工具调用，本轮回答结束
                self._conversation.add_assistant(printed)
                yield TurnFinished(text=printed, rounds=rounds)
                return

            # 把工具调用记入历史，再把执行结果交给模型继续回答
            self._conversation.add_assistant(printed or None, tool_calls=calls)
            for call in calls:
                fn = call["function"]
                name = fn.get("name") or ""
                arguments = fn.get("arguments") or "{}"
                yield ToolCallStarted(name=name, arguments=arguments)
                result = self._registry.execute(name, arguments)
                yield ToolCallFinished(name=name, result=result)
                self._conversation.add_tool_result(call["id"], result)

        yield TurnLimited(rounds=self._max_rounds)

    def _stream_round(self) -> Generator[Event, None, Tuple[str, List[Dict[str, Any]]]]:
        """请求一轮流式回答，产出增量事件，返回 (可见文本, 工具调用列表)。"""
        flt = ThinkFilter()
        printed = ""
        pending: Dict[int, Dict[str, str]] = {}

        stream = self._client.stream(
            self._conversation.messages, tools=self._registry.openai_tools()
        )
        for chunk in stream:
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
