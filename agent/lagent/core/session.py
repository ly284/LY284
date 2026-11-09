"""会话历史：消息序列维护与失败回滚。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

__all__ = ["Conversation"]


class Conversation:
    """对话历史容器。

    只保存 OpenAI 协议消息，不关心它们如何被渲染，
    因此 TUI / Web / Desktop 都可以复用同一份状态。
    """

    def __init__(self, system_prompt: str = "") -> None:
        self._messages: List[Dict[str, Any]] = []
        if system_prompt:
            self._messages.append({"role": "system", "content": system_prompt})

    @property
    def messages(self) -> List[Dict[str, Any]]:
        """返回消息列表副本，外部修改不会污染会话。"""
        return [dict(m) for m in self._messages]

    def __len__(self) -> int:
        return len(self._messages)

    def mark(self) -> int:
        """记录当前位置，用于失败回滚。"""
        return len(self._messages)

    def rollback(self, mark: int) -> None:
        """回到指定位置，丢弃之后的消息。"""
        if 0 <= mark <= len(self._messages):
            del self._messages[mark:]

    def clear(self) -> None:
        self._messages.clear()

    def add(self, message: Dict[str, Any]) -> None:
        self._messages.append(message)

    def insert_after_system(self, message: Dict[str, Any]) -> None:
        """把消息插入到开头的 System Prompt 之后（如 AGENTS.md 指引）。"""
        if self._messages and self._messages[0].get("role") == "system":
            self._messages.insert(1, message)
        else:
            self._messages.insert(0, message)

    def add_user(self, content: str) -> None:
        self._messages.append({"role": "user", "content": content})

    def add_assistant(
        self,
        content: Optional[str],
        tool_calls: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        message: Dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls:
            message["tool_calls"] = tool_calls
        self._messages.append(message)

    def add_tool_result(self, tool_call_id: str, content: str) -> None:
        self._messages.append(
            {"role": "tool", "tool_call_id": tool_call_id, "content": content}
        )

    def transcript(self) -> List[Dict[str, Any]]:
        """给界面层渲染历史用的简化视图（不含 tool_calls 结构）。"""
        out: List[Dict[str, Any]] = []
        for m in self._messages:
            role = m.get("role", "")
            if role == "tool":
                continue
            out.append({"role": role, "content": m.get("content") or ""})
        return out

    def replace_with_summary(self, summary: str) -> None:
        """用压缩摘要替换全部历史消息。

        保留开头的 System Prompt（若有），后续仅保留一条承载摘要的
        user 消息；工具定义仍由 ToolRegistry 提供，不受影响。
        """
        system: Optional[Dict[str, Any]] = None
        if self._messages and self._messages[0].get("role") == "system":
            system = self._messages[0]
        self.clear()
        if system is not None:
            self._messages.append(system)
        self._messages.append({"role": "user", "content": summary})

    def replace_all(self, messages: List[Dict[str, Any]]) -> None:
        """用给定消息列表整体替换会话历史（用于 /resume 恢复会话）。"""
        self._messages = [dict(m) for m in messages]
