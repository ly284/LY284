"""思考内容过滤：剥离 <think> ... 之间的推理文本，兼容流式标签被拆分的情况。"""

from __future__ import annotations

import re
from typing import Tuple

__all__ = ["strip_think", "ThinkFilter"]

_THINK_BLOCK = re.compile(r"‌.*?⣿", re.DOTALL)


def strip_think(text: str) -> str:
    """删除已闭合的思考块，并截掉末尾未闭合的标签/残留。"""
    text = _THINK_BLOCK.sub("", text)
    # 标签还没闭合：思考内容先不输出
    start = text.rfind("‌")
    if start != -1:
        text = text[:start]
    # 末尾是半个标签，等下一段再判断
    tail = text.rfind("<")
    if tail != -1 and ">" not in text[tail:]:
        text = text[:tail]
    return text


class ThinkFilter:
    """累积原始流式文本，只把新增的可见文本吐给调用方。

    关键点：先对累计原文整体做思考块剥离，再与上一次的“累计可见文本”
    比较得出增量。这样标签被拆到不同 chunk 时也不会漏过滤。
    """

    def __init__(self) -> None:
        self._raw = ""
        self._visible = ""

    @property
    def raw(self) -> str:
        return self._raw

    @property
    def visible(self) -> str:
        return self._visible

    def feed(self, delta: str) -> Tuple[str, bool]:
        """喂入一个原始 chunk，返回 (增量可见文本, 是否需要整体替换)。

        `replace=True` 表示这次的可见文本不再以上一次为前缀（例如思考
        块刚闭合、可见文本被重算），界面应整体替换而非追加。
        """
        if not delta:
            return "", False
        self._raw += delta
        now = strip_think(self._raw).strip()

        if now.startswith(self._visible):
            out = now[len(self._visible):]
            self._visible = now
            return out, False

        # 可见文本变短：可能是思考块刚闭合导致重算，等更多 chunk 再定夺
        if self._visible.startswith(now):
            return "", False

        # 不再是前缀关系：整体替换
        self._visible = now
        return now, True
