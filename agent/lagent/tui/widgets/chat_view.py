"""对话记录视图：滚动日志，区分用户、助手、工具与错误消息。"""

from __future__ import annotations

from rich.text import Text
from textual.widgets import RichLog

__all__ = ["ChatView"]

MAX_RESULT_CHARS = 2000


def _clip(text: str, limit: int = MAX_RESULT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n…（已截断，共 {len(text)} 字）"


class ChatView(RichLog):
    """只负责渲染，不含业务逻辑。"""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("wrap", True)
        kwargs.setdefault("highlight", False)
        kwargs.setdefault("markup", False)
        kwargs.setdefault("auto_scroll", True)
        super().__init__(**kwargs)

    def show_user(self, question: str) -> None:
        self.write(Text("你 › ", style="bold cyan") + Text(question))

    def show_answer(self, text: str) -> None:
        if not text.strip():
            return
        self.write(Text("助手 › ", style="bold green"))
        self.write(_clip(text))
        self.write("")

    def show_tool_call(self, name: str, arguments: str) -> None:
        args = (arguments or "").strip()
        if args in ("", "{}"):
            preview = ""
        else:
            preview = f" {args}" if len(args) <= 120 else f" {args[:120]}…"
        self.write(Text(f"⚙ {name}", style="bold yellow") + Text(preview, style="dim"))

    def show_tool_result(self, result: str) -> None:
        for line in _clip(result or "").splitlines() or [""]:
            self.write(Text(f"  {line}", style="dim"))

    def show_error(self, message: str, detail: str = "") -> None:
        self.write(Text(f"✗ {message}", style="bold red"))
        if detail:
            self.write(Text(f"  {detail}", style="red"))
        self.write("")

    def show_info(self, message: str) -> None:
        self.write(Text(message, style="dim italic"))
        self.write("")
