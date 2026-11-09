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
    "ContextUsage",
    "ContextWarning",
    "ContextCompressionStarted",
    "ContextCompressionFinished",
    "ContextCompressionFailed",
    "ContextCompressionSkipped",
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


@dataclass(frozen=True)
class ContextUsage(Event):
    """每轮结束后汇报上下文占用情况（供界面展示长度与百分比）。"""

    used: int
    window: int
    percent: float
    window_default: bool = False
    locked: bool = False


@dataclass(frozen=True)
class ContextWarning(Event):
    """上下文占用达到阈值（默认 60%），提示用户执行 /compact。"""

    used: int
    window: int
    percent: float


@dataclass(frozen=True)
class ContextCompressionStarted(Event):
    """压缩开始；原始上下文已成功归档。"""

    archive_id: str


@dataclass(frozen=True)
class ContextCompressionFinished(Event):
    """压缩成功：摘要已替换会话历史，原始上下文已归档。"""

    archive_id: str
    summary: str
    original: str
    used_after: int


@dataclass(frozen=True)
class ContextCompressionFailed(Event):
    """压缩失败：会话历史保持不变，可重新执行 /compact。"""

    message: str
    detail: str = ""


@dataclass(frozen=True)
class ContextCompressionSkipped(Event):
    """对话历史过短，暂不需要压缩。"""

    reason: str = ""
