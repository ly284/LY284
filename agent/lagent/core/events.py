"""core 输出给界面层的事件契约。

界面层（TUI/Web/Desktop）只依赖这里定义的事件，不感知 LLM SDK 与工具实现。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

__all__ = [
    "Event",
    "AnswerDelta",
    "ToolCallStarted",
    "ToolCallFinished",
    "TurnFinished",
    "TurnLimited",
    "SessionCleared",
    "ErrorEvent",
]


@dataclass(frozen=True)
class Event:
    """所有 core 事件的基类。"""

    @property
    def kind(self) -> str:
        return type(self).__name__

    def as_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, **{k: v for k, v in self.__dict__.items()}}


@dataclass(frozen=True)
class AnswerDelta(Event):
    """回答文本的增量（已过滤思考内容）。"""

    text: str
    replace: bool = False


@dataclass(frozen=True)
class ToolCallStarted(Event):
    """模型请求调用某个工具，尚未执行。"""

    name: str
    arguments: str = ""


@dataclass(frozen=True)
class ToolCallFinished(Event):
    """工具执行完毕，result 为交给模型的原始文本。"""

    name: str
    result: str


@dataclass(frozen=True)
class TurnFinished(Event):
    """一轮问答完成（不再调用工具），text 为最终回答全文。"""

    text: str
    rounds: int = 0


@dataclass(frozen=True)
class TurnLimited(Event):
    """达到最大工具调用轮数，本轮被强制终止。"""

    rounds: int
    text: str = ""


@dataclass(frozen=True)
class SessionCleared(Event):
    """会话历史已被清空。"""


@dataclass(frozen=True)
class ErrorEvent(Event):
    """本轮执行失败，core 已回滚会话历史。"""

    message: str
    detail: Optional[str] = None
