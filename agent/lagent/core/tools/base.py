"""工具注册表：模型可调用的工具声明与分发执行。"""

from __future__ import annotations

import contextvars
import json
import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

__all__ = ["ToolSpec", "ToolRegistry", "ToolError", "ToolCancelled", "get_cancel_event"]

Handler = Callable[..., str]

# 当前轮次的取消信号，通过 contextvar 暴露给每个 handler（如 RunCLI），
# 使长时间阻塞的工具能被 ui 层的中断请求及时终止。
_cancel_var: "contextvars.ContextVar[Optional[threading.Event]]" = contextvars.ContextVar(
    "tool_cancel", default=None
)


def get_cancel_event() -> Optional[threading.Event]:
    """返回当前正在执行工具的取消信号（无则返回 None）。"""
    return _cancel_var.get()


class ToolError(Exception):
    """工具参数或执行错误，消息会回传给模型。"""


class ToolCancelled(Exception):
    """工具执行被用户中断，上层应据此终止本轮，而不是作为错误回传模型。"""


@dataclass(frozen=True)
class ToolSpec:
    """单个工具的声明（名称、描述、JSON Schema 参数、处理函数）。"""

    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Handler

    def to_openai(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def _load_arguments(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        args = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ToolError(f"工具参数不是合法 JSON: {raw}") from exc
    if not isinstance(args, dict):
        raise ToolError(f"工具参数必须是 JSON 对象: {raw}")
    return args


class ToolRegistry:
    """工具集合：负责声明导出与按名分发执行。

    使用线程锁保护注册表，允许 MCP 工具在后台异步加载时与
    模型调用线程并发安全地注册 / 读取。
    """

    def __init__(self) -> None:
        self._tools: Dict[str, ToolSpec] = {}
        self._lock = threading.Lock()

    def register(self, spec: ToolSpec) -> "ToolRegistry":
        with self._lock:
            if spec.name in self._tools:
                raise ValueError(f"工具重名: {spec.name}")
            self._tools[spec.name] = spec
        return self

    def register_many(self, specs: List[ToolSpec]) -> "ToolRegistry":
        for spec in specs:
            self.register(spec)
        return self

    def get(self, name: str) -> Optional[ToolSpec]:
        with self._lock:
            return self._tools.get(name)

    def __contains__(self, name: str) -> bool:
        with self._lock:
            return name in self._tools

    def __len__(self) -> int:
        with self._lock:
            return len(self._tools)

    @property
    def names(self) -> List[str]:
        with self._lock:
            return list(self._tools)

    def openai_tools(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [spec.to_openai() for spec in self._tools.values()]

    def execute(
        self,
        name: str,
        arguments: Optional[str],
        cancel_event: Optional[threading.Event] = None,
    ) -> str:
        """执行工具并返回交给模型的文本结果。

        与原始实现一致：未知工具与执行异常都转成文本回传，不抛出，
        避免单个工具失败中断整轮对话。

        Args:
            cancel_event: 可选的取消信号；会通过 contextvar 暴露给 handler，
                并在调用前检查——已被中断时抛 ToolCancelled（上层据此终止本轮）。
        """
        with self._lock:
            spec = self._tools.get(name)
        if spec is None:
            return f"未找到工具: {name}"
        if cancel_event is not None and cancel_event.is_set():
            raise ToolCancelled()
        try:
            args = _load_arguments(arguments)
            if cancel_event is not None:
                token = _cancel_var.set(cancel_event)
                try:
                    result = spec.handler(**args)
                finally:
                    _cancel_var.reset(token)
            else:
                result = spec.handler(**args)
            return result if isinstance(result, str) else str(result)
        except ToolCancelled:
            raise
        except ToolError as exc:
            return f"工具执行失败: {exc}"
        except TypeError as exc:
            return f"工具执行失败: 参数不匹配 ({exc})"
        except Exception as exc:  # noqa: BLE001 - 错误文本要交给模型判断
            return f"工具执行失败: {exc}"
