"""OpenAI 兼容的流式 LLM 客户端封装。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from openai import OpenAI

from ..config import LLMConfig

__all__ = ["ToolCallDelta", "StreamChunk", "LLMClient"]


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

    @property
    def config(self) -> LLMConfig:
        return self._config

    @property
    def model(self) -> str:
        return self._config.model

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
        }
        tool_list = list(tools) if tools else None
        if tool_list:
            request["tools"] = tool_list

        response = self._client.chat.completions.create(**request)
        for chunk in response:
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
