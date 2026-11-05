"""RunCLI 工具：调用本地已安装的任意命令行程序。

以参数列表（非 shell 拼接）执行，避免命令注入与空白字符问题；
返回标准输出、标准错误与退出码，便于模型判断执行结果。
输出过长时截断并标明，防止占用大量上下文。

说明：本工具用于受控教学实验环境，不包含命令白名单、
黑名单或审批机制，命令以运行 lagent 的当前用户权限执行。
"""

from __future__ import annotations

import locale
import subprocess
import time
from typing import Any, List

from .base import ToolCancelled, ToolSpec, get_cancel_event
from .system_tools import _decode_cmd  # 复用兼容 Windows GBK / UTF-8 的解码逻辑

__all__ = ["build_run_cli", "run_cli"]

_POLL_INTERVAL = 0.25  # 秒，等待期间轮询取消信号的最小间隔

# 合理超时：给交互式/耗时命令足够时间，又避免阻塞对话太久
DEFAULT_TIMEOUT = 60.0
# 输出截断上限：超过后仅保留前后片段并标明截断，避免占用上下文
MAX_OUTPUT_CHARS = 4000
_HEAD_CHARS = 2000
_TAIL_CHARS = 1500


def _truncate(text: str) -> tuple[str, bool]:
    """若超长则保留首尾片段并返回截断标记。"""
    if len(text) <= MAX_OUTPUT_CHARS:
        return text, False
    head, tail = text[:_HEAD_CHARS], text[-_TAIL_CHARS:]
    return (
        f"{head}\n\n...[输出过长，已截断，中间省略 "
        f"{len(text) - _HEAD_CHARS - _TAIL_CHARS} 字符]...\n\n{tail}",
        True,
    )


def _format_result(
    stdout: str, stderr: str, returncode: int, truncated: tuple[bool, bool]
) -> str:
    lines = [f"退出码: {returncode}"]
    if stdout:
        lines.append(f"[stdout]\n{stdout}")
    if stderr:
        lines.append(f"[stderr]\n{stderr}")
    if not stdout and not stderr:
        lines.append("(命令无任何输出)")
    if any(truncated):
        notes = []
        if truncated[0]:
            notes.append("stdout 已截断")
        if truncated[1]:
            notes.append("stderr 已截断")
        lines.append(f"注意: {'，'.join(notes)}")
    return "\n".join(lines)


def run_cli(
    command: str, args: List[str] = [], *, timeout: float = DEFAULT_TIMEOUT
) -> str:
    """执行本地命令行程序并返回 stdout / stderr / 退出码。"""
    if not command or not command.strip():
        return (
            "工具执行失败: 缺少 command，请指明要运行的命令行程序名称，"
            "如 ls、python、git 等"
        )
    argv = [command] + list(args or [])
    cancel_event = get_cancel_event()
    deadline = time.monotonic() + timeout
    timed_out = False
    stdout: bytes = b""
    stderr: bytes = b""
    returncode = -1
    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,  # 明确禁用 shell，避免命令字符串拼接注入
        )
    except FileNotFoundError:
        return f"工具执行失败: 未找到命令行程序 '{command}'，请确认其已安装并在 PATH 中"

    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                proc.kill()
                proc.communicate()
                raise ToolCancelled()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                proc.kill()
                stdout, stderr = proc.communicate()
                timed_out = True
                break
            try:
                stdout, stderr = proc.communicate(timeout=min(_POLL_INTERVAL, remaining))
                returncode = proc.returncode
                break
            except subprocess.TimeoutExpired:
                continue
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or stdout
        stderr = exc.stderr or stderr
        timed_out = True

    returncode = returncode if not timed_out else -1
    stdout = _decode_cmd(stdout)
    stderr = _decode_cmd(stderr)
    stdout, to = _truncate(stdout)
    stderr, te = _truncate(stderr)
    if timed_out:
        head = f"工具执行失败: 命令在 {timeout} 秒内未完成，已终止（可能产出了部分输出）"
        return head + "\n" + _format_result(stdout, stderr, -1, (to, te))
    return _format_result(stdout, stderr, returncode, (to, te))


def build_run_cli() -> ToolSpec:
    """构建 RunCLI 工具的声明。"""
    return ToolSpec(
        name="RunCLI",
        description=(
            "运行本地已安装的任意命令行程序（CLI）。以参数列表方式执行，"
            "不经过 shell。返回标准输出、标准错误与退出码（0 通常表示成功，"
            "非 0 表示出错），以便根据结果决定下一步操作。"
            "超时时间默认 60 秒，输出过长时会被截断并在结果中标明。"
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "command": {
                    "type": "string",
                    "description": (
                        "要运行的命令行程序名称或完整路径，例如 python、git、"
                        "ls 或 C:/Python/python.exe。仅文件名会在 PATH 中查找。"
                    ),
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "传给程序的参数列表，每个参数是独立的字符串数组元素，"
                        "例如 [\"-l\", \".\"], 不要拼成单个长字符串。"
                    ),
                },
                "timeout": {
                    "type": "number",
                    "description": (
                        f"执行超时秒数，超过后终止并返回部分输出，默认 {DEFAULT_TIMEOUT} 秒"
                    ),
                },
            },
            "required": ["command"],
        },
        handler=run_cli,
    )
