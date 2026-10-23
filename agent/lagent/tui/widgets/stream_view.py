"""流式回答预览：实时渲染正在生成的助手文本。"""

from __future__ import annotations

from textual.widgets import Markdown

__all__ = ["StreamView"]

PLACEHOLDER = ""


class StreamView(Markdown):
    """Markdown 预览，回答期间显示，空闲时隐藏。"""

    def __init__(self, **kwargs) -> None:
        super().__init__(PLACEHOLDER, **kwargs)
        self._buffer = ""

    @property
    def buffer(self) -> str:
        return self._buffer

    def append(self, delta: str, replace: bool = False) -> None:
        if replace:
            self._buffer = delta
        else:
            self._buffer += delta
        self.update(self._buffer)

    def finish(self) -> str:
        """结束本轮预览，返回累计文本并清空。"""
        text = self._buffer
        self.clear()
        return text

    def clear(self) -> None:  # type: ignore[override]
        self._buffer = ""
        self.update(PLACEHOLDER)
