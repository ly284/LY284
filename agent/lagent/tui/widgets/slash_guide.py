"""斜杠命令补全引导面板与历史会话恢复面板。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.widgets import Label, ListItem, ListView, Static

from core.session_store import SessionInfo

__all__ = [
    "SLASH_COMMANDS",
    "SlashGuidePanel",
    "ResumePanel",
]

# 全部斜杠命令（TUI 展示与补全共用）
SLASH_COMMANDS: List[Dict[str, str]] = [
    {"command": "/new", "description": "新建会话，并自动保存当前会话历史"},
    {"command": "/resume", "description": "恢复历史会话（列表 ↑↓ 选择 / 回车恢复 / ESC 取消）"},
    {"command": "/save", "description": "保存当前会话到 .agents/sessions"},
    {"command": "/compact", "description": "手动触发上下文压缩（归档原始上下文并生成摘要）"},
    {"command": "/clear", "description": "清屏（仅清空显示，不影响对话历史）"},
    {"command": "/help", "description": "列出全部斜杠命令与常用快捷键帮助"},
    {"command": "/exit", "description": "退出 lagent"},
]

_GUIDE_HINT = "斜杠命令 — 输入前缀筛选 · ↑↓ 选择 · 回车执行"
_RESUME_HINT = "历史会话 — ↑↓ 选择 · 回车恢复 · ESC 取消"


class SlashGuidePanel(Container):
    """输入 `/` 时显示的补全引导面板。"""

    DEFAULT_CSS = """\
    SlashGuidePanel {
        dock: top;
        height: auto;
        max-height: 12;
        display: none;
        border: round $primary;
        background: $panel;
    }
    #guide-title {
        height: 1;
        padding: 0 1;
        color: $accent;
        text-style: bold;
    }
    #guide-list {
        height: auto;
        max-height: 9;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._list: Optional[ListView] = None

    def compose(self) -> ComposeResult:
        yield Static(_GUIDE_HINT, id="guide-title")
        yield ListView(id="guide-list")

    def on_mount(self) -> None:
        self._list = self.query_one("#guide-list", ListView)

    @property
    def list(self) -> ListView:
        if self._list is None:
            self._list = self.query_one("#guide-list", ListView)
        return self._list

    def show_commands(self, commands: List[Dict[str, str]]) -> None:
        """按当前输入前缀显示匹配的命令（并保持高亮在第一个）。"""
        items = [ListItem(Label(f"{c['command']}  —  {c['description']}")) for c in commands]
        self.list.clear()
        self.list.extend(items)
        self.display = True
        if items:
            self.list.index = 0

    def hide_panel(self) -> None:
        self.display = False


class ResumePanel(VerticalScroll):
    """历史会话列表：↑↓ 选择、回车恢复、ESC 取消。"""

    DEFAULT_CSS = """\
    ResumePanel {
        dock: top;
        height: auto;
        max-height: 18;
        display: none;
        border: round $accent;
        background: $panel;
    }
    #resume-title {
        height: 1;
        padding: 0 1;
        color: $accent;
        text-style: bold;
    }
    #resume-list {
        height: auto;
        max-height: 14;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.sessions: List[SessionInfo] = []
        self._list: Optional[ListView] = None

    def compose(self) -> ComposeResult:
        yield Static(_RESUME_HINT, id="resume-title")
        yield ListView(id="resume-list")

    def on_mount(self) -> None:
        self._list = self.query_one("#resume-list", ListView)

    @property
    def list(self) -> ListView:
        if self._list is None:
            self._list = self.query_one("#resume-list", ListView)
        return self._list

    def show_sessions(self, sessions: List[SessionInfo]) -> None:
        self.sessions = list(sessions)
        items = [
            ListItem(
                Label(
                    f"{s.title}  ·  {s.saved_at}  ·  {s.message_count} 条消息  ·  {s.session_id}"
                )
            )
            for s in sessions
        ]
        self.list.clear()
        self.list.extend(items)
        self.display = True
        if items:
            self.list.index = 0
        self.list.focus()

    def hide_panel(self) -> None:
        self.display = False