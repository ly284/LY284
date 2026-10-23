"""Textual TUI 界面：对话主界面。

只依赖 core.events 的事件契约与 core.agent 的引擎接口，
不含任何 LLM / 工具细节，未来 Web / Desktop 界面可按同样方式接入。
"""

from __future__ import annotations

import time

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Footer, Header, Input, Static

from core.agent import AgentEngine
from core.events import (
    AnswerDelta,
    ErrorEvent,
    Event,
    SessionCleared,
    ToolCallFinished,
    ToolCallStarted,
    TurnFinished,
    TurnLimited,
)

from .messages import AgentEventMessage, StreamDeltaMessage
from .widgets.chat_view import ChatView
from .widgets.stream_view import StreamView

__all__ = ["AgentApp"]

FLUSH_INTERVAL = 0.05  # 秒，流式增量合并刷新的最小间隔

STATUS_IDLE = "就绪"
STATUS_THINKING = "思考中…"
STATUS_TOOL = "执行工具…"
STATUS_ERROR = "出错"


class AgentApp(App):
    """lagent 的终端交互界面。"""

    TITLE = "lagent"
    CSS = """
    #chat {
        height: 1fr;
        border-top: tall $accent;
        padding: 0 1;
    }
    #stream {
        height: auto;
        max-height: 40%;
        padding: 0 1;
        border-top: tall $primary;
        background: $panel;
    }
    #status {
        height: 1;
        padding: 0 1;
        background: $surface;
        color: $text-muted;
    }
    #prompt {
        dock: bottom;
    }
    """
    BINDINGS = [
        Binding("ctrl+q", "quit", "退出"),
        Binding("ctrl+l", "clear_chat", "清屏"),
        Binding("ctrl+r", "reset_session", "重置会话"),
    ]

    def __init__(self, engine: AgentEngine) -> None:
        super().__init__()
        self._engine = engine
        self._busy = False

    # ---------- 布局 ----------

    def compose(self) -> ComposeResult:
        yield Header()
        yield ChatView(id="chat")
        yield StreamView(id="stream")
        yield Static(STATUS_IDLE, id="status")
        yield Input(placeholder="输入问题，回车发送；ctrl+q 退出", id="prompt")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#stream", StreamView).display = False
        self.query_one("#prompt", Input).focus()

    # ---------- 事件入口 ----------

    @on(Input.Submitted, "#prompt")
    def handle_submit(self, event: Input.Submitted) -> None:
        question = event.value.strip()
        event.input.value = ""
        if not question:
            return
        if question == "exit":
            self.exit()
            return
        if self._busy:
            self.notify("上一个问题尚未完成，请稍候", severity="warning")
            return
        self._busy = True
        self.query_one("#prompt", Input).disabled = True
        self.query_one("#status", Static).update(STATUS_THINKING)
        self.query_one(ChatView).show_user(question)
        self.run_turn(question)

    # ---------- 工作线程 ----------

    @work(thread=True, exclusive=True, group="turn")
    def run_turn(self, question: str) -> None:
        """在线程中消费 core 事件流，合并流式增量后回投给界面。"""
        pending = []
        last_flush = time.monotonic()

        def flush(replace: bool = False) -> None:
            nonlocal pending, last_flush
            if not pending:
                return
            text = "".join(pending)
            pending = []
            last_flush = time.monotonic()
            self.post_message(StreamDeltaMessage(text, replace))

        try:
            for event in self._engine.ask(question):
                if isinstance(event, AnswerDelta):
                    pending.append(event.text)
                    if time.monotonic() - last_flush >= FLUSH_INTERVAL:
                        flush(replace=event.replace)
                    continue
                flush()
                self.post_message(AgentEventMessage(event))
        except Exception as exc:  # noqa: BLE001 - 兜底，避免线程静默失败
            flush()
            self.post_message(AgentEventMessage(ErrorEvent(message=str(exc))))
        finally:
            flush()

    # ---------- 事件处理 ----------

    def on_agent_event_message(self, message: AgentEventMessage) -> None:
        event = message.event
        if isinstance(event, ToolCallStarted):
            self._set_status(STATUS_TOOL)
            self.query_one(ChatView).show_tool_call(event.name, event.arguments)
        elif isinstance(event, ToolCallFinished):
            self.query_one(ChatView).show_tool_result(event.result)
            self._set_status(STATUS_THINKING)
        elif isinstance(event, TurnFinished):
            self._finish_stream()
            self.query_one(ChatView).show_answer(event.text)
            self._set_idle()
        elif isinstance(event, TurnLimited):
            self._finish_stream()
            self.query_one(ChatView).show_info(
                f"已达到最大工具调用轮数（{event.rounds}），本轮终止"
            )
            self._set_idle()
        elif isinstance(event, SessionCleared):
            self.query_one(ChatView).clear()
            self.query_one(StreamView).clear()
            self.query_one(StreamView).display = False
            self.notify("会话已重置")
        elif isinstance(event, ErrorEvent):
            self._finish_stream()
            self.query_one(ChatView).show_error(event.message, event.detail or "")
            self._set_status(STATUS_ERROR)
            self._set_idle(error=True)

    def on_stream_delta_message(self, message: StreamDeltaMessage) -> None:
        stream = self.query_one("#stream", StreamView)
        if not stream.display:
            stream.display = True
        stream.append(message.text, replace=message.replace)

    # ---------- 内部工具 ----------

    def _finish_stream(self) -> None:
        stream = self.query_one(StreamView)
        text = stream.finish()
        stream.display = False
        if text.strip():
            self.query_one(ChatView).show_answer(text)

    def _set_status(self, text: str) -> None:
        self.query_one("#status", Static).update(text)

    def _set_idle(self, error: bool = False) -> None:
        self._busy = False
        self.query_one("#prompt", Input).disabled = False
        self.query_one("#prompt", Input).focus()
        self._set_status(STATUS_IDLE if not error else STATUS_ERROR)

    # ---------- 动作 ----------

    def action_clear_chat(self) -> None:
        self.query_one(ChatView).clear()

    def action_reset_session(self) -> None:
        if self._busy:
            self.notify("正在处理中，无法重置", severity="warning")
            return
        self.post_message(AgentEventMessage(self._engine.reset()))
