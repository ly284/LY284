"""OpenAI 兼容的流式 LLM 客户端封装。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from openai import OpenAI

from ..config import LLMConfig

__all__ = ["ToolCallDelta", "StreamChunk", "LLMClient"]

DEFAULT_TIMEOUT = 120.0  # 秒，单次请求超时上限，避免网络挂起时无法恢复


@dataclass(frozen=True)
class ToolCallDelta:
    """流式到达的工具调用片段。"""

    index: int
    id: str = ""
    name: str = ""
    arguments: str = ""


@dataclass(frozen=True)
class StreamChunk:
    """一次流式增量：文本片段和/或工具调用片段。"""

    text: str = ""
    tool_calls: Tuple[ToolCallDelta, ...] = ()


class LLMClient:
    """把 OpenAI SDK 的流式响应整理成 StreamChunk 序列。

    该类只负责“怎么和模型通信”，不关心对话上下文与工具编排，
    因此换模型服务（LM Studio / SiliconFlow / 官方 OpenAI）都无需改上层。
    """

    def __init__(self, config: LLMConfig, *, timeout: Optional[float] = None) -> None:
        self._config = config
        kwargs: Dict[str, Any] = {
            "api_key": config.api_key,
            "base_url": config.base_url,
        }
        if timeout is not None:
            kwargs["timeout"] = timeout
        self._client = OpenAI(**kwargs)
        self._last_usage: Optional[int] = None

    @property
    def config(self) -> LLMConfig:
        return self._config

    @property
    def model(self) -> str:
        return self._config.model

    @property
    def last_usage(self) -> Optional[int]:
        """最近一次请求的 Token 使用量（total_tokens）；拿不到时为 None。"""
        return self._last_usage

    def stream(
        self,
        messages: Sequence[Dict[str, Any]],
        tools: Optional[Iterable[Dict[str, Any]]] = None,
    ) -> Iterator[StreamChunk]:
        """发起流式对话请求，逐块产出 StreamChunk。

        Args:
            messages: OpenAI 协议的消息列表。
            tools: OpenAI 协议的工具声明列表，为空时传 None。
        """
        request: Dict[str, Any] = {
            "model": self._config.model,
            "messages": list(messages),
            "stream": True,
            # 请求最终的 usage 统计，便于上层获取真实 Token 用量
            "stream_options": {"include_usage": True},
        }
        tool_list = list(tools) if tools else None
        if tool_list:
            request["tools"] = tool_list

        self._last_usage = None
        response = self._client.chat.completions.create(**request)
        for chunk in response:
            usage = getattr(chunk, "usage", None)
            if usage is not None:
                total = getattr(usage, "total_tokens", None)
                if total:
                    self._last_usage = int(total)
            if not getattr(chunk, "choices", None):
                continue
            delta = chunk.choices[0].delta
            text = getattr(delta, "content", None) or ""
            call_deltas: List[ToolCallDelta] = []
            for tc in getattr(delta, "tool_calls", None) or []:
                fn = getattr(tc, "function", None)
                call_deltas.append(
                    ToolCallDelta(
                        index=getattr(tc, "index", 0) or 0,
                        id=getattr(tc, "id", "") or "",
                        name=getattr(fn, "name", "") or "",
                        arguments=getattr(fn, "arguments", "") or "",
                    )
                )
            if text or call_deltas:
                yield StreamChunk(text=text, tool_calls=tuple(call_deltas))

    def complete(
        self,
        messages: Sequence[Dict[str, Any]],
        *,
        max_tokens: Optional[int] = None,
        temperature: float = 0.3,
    ) -> str:
        """发起非流式对话请求，返回完整回答文本（用于上下文压缩等场景）。"""
        request: Dict[str, Any] = {
            "model": self._config.model,
            "messages": list(messages),
            "stream": False,
            "temperature": temperature,
        }
        if max_tokens is not None:
            request["max_tokens"] = max_tokens

        response = self._client.chat.completions.create(**request)
        usage = getattr(response, "usage", None)
        if usage is not None:
            total = getattr(usage, "total_tokens", None)
            if total:
                self._last_usage = int(total)
        return getattr(response.choices[0].message, "content", None) or ""

    def fetch_context_window(self, timeout: float = 3.0) -> Optional[int]:
        """尝试从模型服务查询当前模型的上下文窗口大小。

        拿不到时返回 None，由上层回退到默认 128k（并标记「默认」）。
        """
        try:
            model_obj = self._client.models.retrieve(
                self._config.model, timeout=timeout
            )
        except Exception:  # noqa: BLE001 - 查询失败只是回退默认值，不阻断
            return None

        if isinstance(model_obj, dict):
            data = model_obj
        else:
            data = getattr(model_obj, "model_dump", lambda: {})()
            if not data:
                data = {}
                for attr in ("context_length", "context_window", "max_context"):
                    if getattr(model_obj, attr, None) is not None:
                        data = {"context_length": getattr(model_obj, attr)}
                        break

        for key in ("context_length", "context_window", "max_context", "max_context_length"):
            value = data.get(key)
            if isinstance(value, (int, float)) and int(value) > 0:
                return int(value)
        # 某些服务把元信息放在 meta 里
        meta = data.get("meta") or {}
        if isinstance(meta, dict):
            for key in ("context_length", "context_window", "max_context"):
                value = meta.get(key)
                if isinstance(value, (int, float)) and int(value) > 0:
                    return int(value)
        return None
