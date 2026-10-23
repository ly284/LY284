"""TUI 消息：core 事件与流式增量 → Textual Message。

界面层只依赖 core.events 的事件契约，不感知 LLM SDK 与工具实现。
"""

from __future__ import annotations

from textual.message import Message

from core.events import Event

__all__ = ["AgentEventMessage", "StreamDeltaMessage"]


class AgentEventMessage(Message):
    """一条 core 事件（工具调用、轮次结束、错误等）。"""

    def __init__(self, event: Event) -> None:
        super().__init__()
        self.event = event


class StreamDeltaMessage(Message):
    """已经合并过的流式文本增量，避免逐 chunk 刷新界面。"""

    def __init__(self, text: str, replace: bool = False) -> None:
        super().__init__()
        self.text = text
        self.replace = replace
