"""Textual TUI 界面：对话主界面。

只依赖 core.events 的事件契约与 core.agent 的引擎接口，
不含任何 LLM / 工具细节，未来 Web / Desktop 界面可按同样方式接入。
"""

from __future__ import annotations

import threading
import time

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, ListView, Static

from core.agent import AgentEngine, TurnCancelled
from core.events import (
    AnswerDelta,
    ContextCompressionFinished,
    ContextCompressionSkipped,
    ContextCompressionStarted,
    ContextUsage,
    ContextWarning,
    ErrorEvent,
    Event,
    SessionCleared,
    ToolCallFinished,
    ToolCallStarted,
    TurnFinished,
    TurnLimited,
)

from .messages import (
    AgentEventMessage,
    StreamDeltaMessage,
    TurnInterruptedMessage,
)
from .widgets.chat_view import ChatView
from .widgets.context_panel import ContextPreviewPanel
from .widgets.mcp_panel import MCPPanel
from .widgets.slash_guide import ResumePanel, SLASH_COMMANDS, SlashGuidePanel
from .widgets.stream_view import StreamView

__all__ = ["AgentApp"]

FLUSH_INTERVAL = 0.05  # 秒，流式增量合并刷新的最小间隔

STATUS_IDLE = "就绪"
STATUS_THINKING = "思考中…"
STATUS_TOOL = "执行工具…"
STATUS_COMPRESSING = "正在压缩上下文…"
STATUS_ERROR = "出错"

COMPACT_COMMAND = "/compact"

HELP_TEXT = """\
可用斜杠命令（输入框输入 `/` 自动弹出补全引导）：
  /new       新建会话，并自动保存当前会话历史
  /resume    恢复历史会话（弹列表：↑↓ 选择、回车恢复、ESC 取消）
  /save      保存当前会话到 .agents/sessions/
  /compact   手动触发上下文压缩（归档原始上下文并生成摘要）
  /clear     清屏（仅清空显示，不影响对话历史）
  /help      查看本帮助
  /exit      退出 lagent

常用快捷键：
  Ctrl+Q     退出
  Ctrl+L     清屏
  Ctrl+R     重置会话（保留 System Prompt 与 AGENTS.md 指引）
  Esc/Ctrl+C 打断当前生成或工具执行"""


class ConfigHintScreen(ModalScreen[None]):
    """首次启动缺少 config.ini 时弹出的提示对话框。"""

    DEFAULT_CSS = """
    ConfigHintScreen {
        align: center middle;
        background: $boost 80%;
    }
    #config-hint-box {
        width: 72;
        height: auto;
        padding: 2 3;
        border: heavy $accent;
        background: $surface;
    }
    """

    def __init__(self, path: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._path = path

    def compose(self) -> ComposeResult:
        with Vertical(id="config-hint-box"):
            yield Static(
                "未找到配置文件 config.ini",
                classes="config-hint-title",
            )
            yield Static(
                (
                    "程序已为你创建示例配置文件：\n"
                    f"{self._path}\n\n"
                    "里面填入了 mock 的 api_key。请用编辑器打开该文件，\n"
                    "填入你自己的模型服务地址、模型名称与 API Key，\n"
                    "然后重新启动 lagent 才能正常工作。"
                )
            )
            yield Button("知道了，退出程序", id="config-hint-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "config-hint-close":
            self.app.exit()


class PasteInput(Input):
    """单行输入框，粘贴内容会完整折叠为一行，绝不把换行当成提交。

    修正：原生 Input 对粘贴多行的处理可能只保留第一行/把换行当回车，
    这里接管粘贴事件，把 \\r\\n / \\r / \\n 统一折叠为空格后再插入，
    这样所有内容都保留、且不会误触发发送。
    """

    def _on_paste(self, event) -> None:
        raw = getattr(event, "text", "") or ""
        folded = (
            raw.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
            if raw
            else ""
        )
        if folded:
            self.insert(folded, len(self.value))
        event.prevent_default()
        event.stop()


class AgentApp(App):
    """lagent 的终端交互界面。"""

    TITLE = "lagent"
    CSS = """
    #ctx-status {
        height: 1;
        padding: 0 1;
        background: $boost;
        color: $text;
        border-bottom: solid $primary;
    }
    #main-area {
        height: 1fr;
    }
    #mcp-panel {
        width: 34;
        height: 1fr;
        border-right: tall $primary;
        background: $surface;
        padding: 0 1;
    }
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
        Binding("escape", "stop", "打断"),
        Binding("ctrl+c", "stop", "打断"),
        Binding("up", "slash_up", "上移"),
        Binding("down", "slash_down", "下移"),
    ]

    def __init__(self, engine: AgentEngine, config_hint: Optional[str] = None) -> None:
        super().__init__()
        self._engine = engine
        self._busy = False
        self._cancel: threading.Event | None = None
        self._context_locked = False
        self._config_hint = config_hint

    # ---------- 布局 ----------

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("上下文: -- / --", id="ctx-status")
        yield SlashGuidePanel(id="guide-panel")
        yield ContextPreviewPanel()
        yield ResumePanel(id="resume-panel")
        with Horizontal(id="main-area"):
            yield MCPPanel(id="mcp-panel")
            with Vertical():
                yield ChatView(id="chat")
                yield StreamView(id="stream")
                yield Static(STATUS_IDLE, id="status")
        yield PasteInput(
            placeholder="输入问题回车发送；/ 弹出命令补全；Esc / Ctrl+C 打断；ctrl+q 退出",
            id="prompt",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#stream", StreamView).display = False
        self.query_one(ContextPreviewPanel).display = False
        self.query_one(SlashGuidePanel).display = False
        self.query_one(ResumePanel).display = False
        self.query_one("#prompt", Input).focus()
        usage = self._engine.context_usage()
        self._context_locked = bool(usage["locked"])
        self._update_context_display(usage)
        # MCP 侧边栏：异步加载，先进入界面后每隔 1 秒轮询刷新
        self.set_interval(1.0, self._refresh_mcp)
        if self._config_hint:
            self.push_screen(ConfigHintScreen(self._config_hint))

    def _refresh_mcp(self) -> None:
        self.query_one("#mcp-panel", MCPPanel).refresh_status(self._engine.mcp_status())

    # ---------- 事件入口 ----------

    @on(Input.Submitted, "#prompt")
    def handle_submit(self, event: Input.Submitted) -> None:
        """回车提交（粘贴换行已被 PasteInput 折叠，不会误触发）。"""
        question = event.value.rstrip()
        event.input.value = ""
        if question.startswith("/"):
            resolved = self._resolve_slash(question)
            if resolved is not None:
                question = resolved
        self._dispatch(question)

    @on(Input.Changed, "#prompt")
    def on_input_changed(self, event: Input.Changed) -> None:
        """输入前缀为 / 时弹出补全引导面板，前缀匹配时逐字筛选。"""
        if self._busy:
            self.query_one(SlashGuidePanel).display = False
            return
        value = event.value
        if value.startswith("/"):
            matches = [c for c in SLASH_COMMANDS if c["command"].startswith(value)]
            if matches:
                self.query_one(SlashGuidePanel).show_commands(matches)
                return
        self.query_one(SlashGuidePanel).display = False

    def _resolve_slash(self, value: str) -> Optional[str]:
        """把 / 前缀解析成完整命令（精确命中或唯一前缀补全）。"""
        value = value.strip()
        if not value.startswith("/"):
            return None
        for c in SLASH_COMMANDS:
            if value == c["command"]:
                return value
        matches = [c["command"] for c in SLASH_COMMANDS if c["command"].startswith(value)]
        if len(matches) == 1:
            return matches[0]
        return None

    def _dispatch(self, question: str) -> None:
        if not question:
            return
        if question == "exit" or question == "/exit":
            self.exit()
            return
        if self._busy:
            self.notify("上一个问题尚未完成，请稍候", severity="warning")
            return
        if question.startswith("/"):
            self._run_slash_command(question)
            return
        if self._context_locked:
            self.notify(
                "上下文占用已超过阈值，请先执行 /compact 压缩上下文后再继续提问",
                severity="warning",
            )
            return
        self._busy = True
        self._cancel = threading.Event()
        self.query_one("#prompt", Input).disabled = True
        self.query_one("#status", Static).update(STATUS_THINKING)
        self.query_one(ChatView).show_user(question)
        self.run_turn(question, self._cancel)

    # ---------- 斜杠命令 ----------

    def _run_slash_command(self, question: str) -> None:
        command = question.split()[0]
        self.query_one(SlashGuidePanel).display = False
        if command == "/new":
            self._slash_new()
        elif command == "/save":
            self._slash_save()
        elif command == "/resume":
            self._slash_resume()
        elif command == "/compact":
            self._start_compact()
        elif command == "/clear":
            self.query_one(ChatView).clear()
            self.notify("已清屏")
        elif command == "/help":
            self.query_one(ChatView).show_info(HELP_TEXT)
        else:
            self.query_one(ChatView).show_info(
                f"未知命令: {command}。输入 /help 查看可用命令"
            )

    def _slash_new(self) -> None:
        """/new：自动保存当前会话，然后新建会话。"""
        saved = self._engine.save_session()
        self.post_message(AgentEventMessage(self._engine.reset()))
        if saved is not None:
            self.query_one(ChatView).show_info(
                f"已自动保存当前会话: {saved.session_id}（{saved.message_count} 条消息），开始新会话"
            )
        else:
            self.query_one(ChatView).show_info("已新建会话（当前会话没有可保存的对话内容）")

    def _slash_save(self) -> None:
        """/save：保存当前会话。"""
        info = self._engine.save_session()
        if info is None:
            self.query_one(ChatView).show_info("当前会话还没有可保存的对话内容")
        else:
            self.query_one(ChatView).show_info(
                f"会话已保存: {info.session_id} · {info.title} → {info.path}"
            )

    def _slash_resume(self) -> None:
        """/resume：弹出历史会话列表，↑↓ 选择、回车恢复、ESC 取消。"""
        sessions = self._engine.list_sessions()
        if not sessions:
            self.query_one(ChatView).show_info("还没有保存过的会话，请先使用 /save 保存")
            return
        self.query_one(ResumePanel).show_sessions(sessions)

    def _restore_session(self, session) -> None:
        messages = self._engine.resume_session(session.session_id)
        if messages is None:
            self.query_one(ChatView).show_info(f"无法恢复会话 {session.session_id}")
            return
        chat = self.query_one(ChatView)
        chat.clear()
        chat.show_transcript(messages)
        self._context_locked = False
        self._update_context_display(self._engine.context_usage())
        chat.show_info(f"已恢复会话 {session.session_id}（{session.title}）")

    @on(ListView.Selected, "#resume-list")
    def on_resume_selected(self, event: ListView.Selected) -> None:
        panel = self.query_one(ResumePanel)
        index = panel.list.index
        if index is None or index >= len(panel.sessions):
            panel.hide_panel()
            return
        session = panel.sessions[index]
        panel.hide_panel()
        self.query_one("#prompt", Input).focus()
        self._restore_session(session)

    def _start_compact(self) -> None:
        """手动触发上下文压缩（/compact）。"""
        self._busy = True
        self._cancel = threading.Event()
        self.query_one("#prompt", Input).disabled = True
        self._set_status(STATUS_COMPRESSING)
        self.query_one(ChatView).show_info(
            "开始上下文压缩…（压缩期间不可提问，也不允许调用其它工具）"
        )
        self.run_compact(self._cancel)

    # ---------- 引导面板方向键 ----------

    def action_slash_up(self) -> None:
        resume = self.query_one(ResumePanel)
        if resume.display:
            resume.list.highlight_previous()
            return
        guide = self.query_one(SlashGuidePanel)
        if guide.display:
            guide.list.highlight_previous()

    def action_slash_down(self) -> None:
        resume = self.query_one(ResumePanel)
        if resume.display:
            resume.list.highlight_next()
            return
        guide = self.query_one(SlashGuidePanel)
        if guide.display:
            guide.list.highlight_next()

    def action_stop(self) -> None:
        """Esc：忙碌时打断当前操作；空闲时先关闭引导 / 恢复面板。"""
        resume = self.query_one(ResumePanel)
        guide = self.query_one(SlashGuidePanel)
        if self._busy:
            if self._cancel is not None:
                self._cancel.set()
                self.query_one("#status", Static).update("正在打断…")
            return
        if resume.display:
            resume.hide_panel()
            self.query_one("#prompt", Input).focus()
            return
        if guide.display:
            guide.hide_panel()
            return

    # ---------- 工作线程 ----------

    @work(thread=True, exclusive=True, group="turn")
    def run_turn(self, question: str, cancel_event: threading.Event) -> None:
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
            for event in self._engine.ask(question, cancel_event):
                if isinstance(event, AnswerDelta):
                    pending.append(event.text)
                    if time.monotonic() - last_flush >= FLUSH_INTERVAL:
                        flush(replace=event.replace)
                    continue
                flush()
                self.post_message(AgentEventMessage(event))
        except TurnCancelled:
            flush()
            self.post_message(TurnInterruptedMessage())
        except Exception as exc:  # noqa: BLE001 - 兜底，避免线程静默失败
            flush()
            self.post_message(AgentEventMessage(ErrorEvent(message=str(exc))))
        finally:
            flush()

    @work(thread=True, exclusive=True, group="turn")
    def run_compact(self, cancel_event: threading.Event) -> None:
        """在线程中执行上下文压缩，消费 core 的压缩事件流。"""
        try:
            for event in self._engine.compact(cancel_event):
                self.post_message(AgentEventMessage(event))
        except TurnCancelled:
            self.post_message(TurnInterruptedMessage())
        except Exception as exc:  # noqa: BLE001 - 兜底，避免线程静默失败
            self.post_message(AgentEventMessage(ErrorEvent(message=str(exc))))

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
            self._context_locked = False
            self._update_context_display(self._engine.context_usage())
            self.notify("会话已重置")
        elif isinstance(event, ErrorEvent):
            self._finish_stream()
            self.query_one(ChatView).show_error(event.message, event.detail or "")
            self._set_status(STATUS_ERROR)
            self._set_idle(error=True)
        elif isinstance(event, ContextUsage):
            self._update_context_display(
                {
                    "used": event.used,
                    "window": event.window,
                    "percent": event.percent,
                    "window_default": event.window_default,
                    "locked": event.locked,
                }
            )
        elif isinstance(event, ContextWarning):
            self._context_locked = True
            self.notify(
                f"上下文占用已达 {event.percent * 100:.0f}%（{event.used / 1000:.1f}k / "
                f"{event.window / 1000:.0f}k），请执行 /compact 压缩上下文",
                severity="warning",
                timeout=6,
            )
        elif isinstance(event, ContextCompressionStarted):
            self._set_status(STATUS_COMPRESSING)
            self.query_one(ChatView).show_info(
                f"原始上下文已保存到归档 {event.archive_id}，正在生成摘要…"
            )
        elif isinstance(event, ContextCompressionFinished):
            panel = self.query_one(ContextPreviewPanel)
            panel.show_context(event.original, event.summary)
            self._context_locked = False
            usage = self._engine.context_usage()
            usage["used"] = event.used_after
            usage["percent"] = event.used_after / max(1, usage["window"])
            usage["locked"] = False
            self._update_context_display(usage)
            self._set_idle()
            self.notify(
                f"上下文压缩成功（归档 {event.archive_id}），输入限制已解除",
                severity="information",
                timeout=4,
            )
        elif isinstance(event, ContextCompressionFailed):
            self._set_status(STATUS_ERROR)
            self.query_one(ChatView).show_error(event.message, event.detail or "")
            self._set_idle(error=True)
            self.notify(
                "压缩失败，原始上下文已保留，可重新执行 /compact",
                severity="error",
                timeout=6,
            )
        elif isinstance(event, ContextCompressionSkipped):
            self.query_one(ChatView).show_info(event.reason)
            self._set_idle()
            self.notify(event.reason, timeout=4)

    def on_turn_interrupted_message(self, message: TurnInterruptedMessage) -> None:
        stream = self.query_one(StreamView)
        stream.clear()
        stream.display = False
        self.notify("已打断当前操作")
        self._set_idle()

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

    def _update_context_display(self, usage: dict) -> None:
        """更新顶部上下文占用显示：长度 k / 窗口 k / 百分比（无法获取窗口时标「默认」）。"""
        window = int(usage.get("window") or 0)
        used = int(usage.get("used") or 0)
        percent = float(usage.get("percent") or 0.0) * 100
        tag = " 默认" if usage.get("window_default") else ""
        locked = " · 🔒 已锁定（请先 /compact）" if usage.get("locked") else ""
        text = f"上下文: {used / 1000:.1f}k / {window / 1000:.0f}k（已占用 {percent:.0f}%）{tag}{locked}"
        self.query_one("#ctx-status", Static).update(text)

    def _set_idle(self, error: bool = False) -> None:
        self._busy = False
        self._cancel = None
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
        self.query_one(ContextPreviewPanel).display = False
        self.query_one(ResumePanel).hide_panel()
        self.query_one(SlashGuidePanel).hide_panel()
        self.post_message(AgentEventMessage(self._engine.reset()))
