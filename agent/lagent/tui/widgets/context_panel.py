"""压缩预览面板：左右两栏对比显示“压缩前原文”与“压缩后摘要”。"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Button, RichLog, Static

__all__ = ["ContextPreviewPanel"]


def _write_lines(log: RichLog, text: str) -> None:
    """把大段文本写入 RichLog（逐行写入，超长行折叠显示）。"""
    for line in (text or "").splitlines():
        log.write(line)
        log.write(" ")


class ContextPreviewPanel(Horizontal):
    """上下文压缩结果面板。

    - 左侧：压缩前原文（可滚动）
    - 右侧：压缩后摘要（可滚动）
    - “关闭”按钮：关闭面板
    """

    DEFAULT_CSS = """
    ContextPreviewPanel {
        height: 60%;
        dock: top;
        border: heavy $accent;
        padding: 0 1;
        display: none;
    }

    ContextPreviewPanel .ctx-col {
        width: 1fr;
        height: 1fr;
        border: round $primary;
        margin: 1;
    }

    ContextPreviewPanel .ctx-title {
        height: auto;
        padding: 0 1;
        color: $accent;
        text-style: bold;
    }

    #ctx-original, #ctx-summary {
        height: 1fr;
    }

    #ctx-close-panel {
        margin: 1 1;
    }
    """

    def __init__(self, original: str = "", summary: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self._original = original
        self._summary = summary

    def compose(self) -> ComposeResult:
        with Container(classes="ctx-col"):
            yield Static("原始上下文（压缩前）｜可滚动", classes="ctx-title")
            yield RichLog(
                wrap=True,
                markup=False,
                highlight=False,
                auto_scroll=False,
                id="ctx-original",
            )
        with Container(classes="ctx-col"):
            yield Static("压缩摘要（压缩后）｜可滚动", classes="ctx-title")
            yield RichLog(
                wrap=True,
                markup=False,
                highlight=False,
                auto_scroll=False,
                id="ctx-summary",
            )
        yield Button("关闭", id="ctx-close-panel", variant="primary")

    def on_mount(self) -> None:
        self._fill()

    def show_context(self, original: str, summary: str) -> None:
        """更新内容并显示面板。"""
        self._original = original
        self._summary = summary
        if self.is_mounted:
            self._fill()
        self.display = True

    def hide_panel(self) -> None:
        self.display = False

    def refresh_columns(self) -> None:
        self._fill()

    def _fill(self) -> None:
        origin = self.query_one("#ctx-original", RichLog)
        summary = self.query_one("#ctx-summary", RichLog)
        origin.clear()
        summary.clear()
        _write_lines(origin, self._original)
        _write_lines(summary, self._summary)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ctx-close-panel":
            self.hide_panel()