"""Beatra 工具：把本地安装的 beatra Skill 的 MCP 客户端暴露给模型。

通过项目内 skills/beatra/scripts/mcp_client.py 调用 Beatra 的图片、视频、
音乐、语音与公开社交数据等能力。客户端只使用 Python 标准库，要求
Python 3.10+，无需在 command 参数里塞入任何凭据或路径（凭据在
~/.beatra/ 下、由 authorize 授权产生）。

调用约束与收费边界详见 skills/beatra/SKILL.md 及各 references/ 文档，
本文件只负责把客户端命令接到工具注册表。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from .base import ToolError, ToolSpec

__all__ = ["build_beatra_tools"]

#: 项目内 beatra Skill 的 scripts 目录（相对本文件：core/tools -> 项目根/skills/beatra/scripts）
_SKILL_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "skills" / "beatra" / "scripts"
_MCP_CLIENT = _SKILL_SCRIPTS / "mcp_client.py"

DEFAULT_TIMEOUT = 300.0
MAX_OUTPUT_CHARS = 6000
_HEAD_CHARS = 3000
_TAIL_CHARS = 2500


def _find_python3() -> str:
    """找一个满足 Python 3.10+ 的解释器：优先 Windows 的 py -3，其次 python3。"""
    if os.name == "nt":
        launcher = shutil.which("py")
        if launcher:
            return launcher
    return shutil.which("python3") or shutil.which("python") or "python"


def _pylib_major_minor(argv_python: List[str]) -> Optional[tuple[int, int]]:
    """返回解释器的 (major, minor)，失败时返回 None。"""
    try:
        proc = subprocess.run(
            argv_python + ["-c", "import sys;print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            input=b"",
            capture_output=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    try:
        major, minor = proc.stdout.decode().strip().split(".")
        return int(major), int(minor)
    except (ValueError, AttributeError):
        return None


def _python_argv() -> List[str]:
    """构造实际调用解释器的 argv 前缀。"""
    if os.name == "nt":
        launcher = shutil.which("py")
        if launcher:
            return [launcher, "-3"]
    base = _find_python3()
    version = _pylib_major_minor([base])
    if version is not None and version >= (3, 10):
        return [base]
    return [base]


def _truncate(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text, False
    head, tail = text[:_HEAD_CHARS], text[-_TAIL_CHARS:]
    return (
        f"{head}\n\n...[输出过长已截断，中间省略 {len(text) - _HEAD_CHARS - _TAIL_CHARS} 字符]...\n\n{tail}",
        True,
    )


def _format_result(stdout: str, stderr: str, returncode: int, truncated: tuple[bool, bool]) -> str:
    lines = [f"退出码: {returncode}"]
    if stdout:
        lines.append(f"[stdout]\n{stdout}")
    if stderr:
        lines.append(f"[stderr]\n{stderr}")
    if not stdout and not stderr:
        lines.append("(无任何输出)")
    if any(truncated):
        notes = []
        if truncated[0]:
            notes.append("stdout 已截断")
        if truncated[1]:
            notes.append("stderr 已截断")
        lines.append(f"注意: {'，'.join(notes)}")
    return "\n".join(lines)


def _run_cli(argv: List[str], stdin: bytes = b"") -> str:
    """运行客户端命令并把退出码/stdout/stderr 整理成给模型的文本。"""
    if not _MCP_CLIENT.is_file():
        raise ToolError(f"未找到 beatra 客户端: {_MCP_CLIENT}；请先安装 beatra Skill")
    try:
        proc = subprocess.run(
            argv, input=stdin, capture_output=True, timeout=DEFAULT_TIMEOUT, shell=False
        )
    except FileNotFoundError as exc:
        raise ToolError(f"无法定位 Python 解释器以运行 beatra 客户端: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or b"").decode("utf-8", errors="replace")
        stderr = (exc.stderr or b"").decode("utf-8", errors="replace")
        stdout, to = _truncate(stdout)
        stderr, te = _truncate(stderr)
        head = f"工具执行失败: beatra 客户端在 {DEFAULT_TIMEOUT} 秒内未完成，已终止（可能产出部分输出）"
        return head + "\n" + _format_result(stdout, stderr, -1, (to, te))
    stdout = proc.stdout.decode("utf-8", errors="replace")
    stderr = proc.stderr.decode("utf-8", errors="replace")
    stdout, to = _truncate(stdout)
    stderr, te = _truncate(stderr)
    return _format_result(stdout, stderr, proc.returncode, (to, te))


def _beatra_call(
    tool: str, arguments_json: str = "{}", *, authorization: bool = True
) -> str:
    """调用一个 Beatra MCP 工具，参数通过 stdin 传 JSON。"""
    tool = (tool or "").strip()
    if not tool:
        raise ToolError("缺少 tool 参数：要调用的 Beatra 工具名")
    if not (arguments_json or "").strip():
        arguments_json = "{}"
    try:
        payload = json.loads(arguments_json)
    except json.JSONDecodeError as exc:
        raise ToolError(f"arguments_json 不是合法 JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ToolError("arguments_json 必须是 JSON 对象")
    stdin = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return _cli_call("call", [tool], stdin)


def _cli_call(subcommand: str, args: List[str], stdin: bytes = b"") -> str:
    prefix = _python_argv()
    return _run_cli(
        [*prefix, str(_MCP_CLIENT), subcommand, *args],
        stdin=stdin,
    )


def _beatra_authorize() -> str:
    """发起或恢复 Beatra 设备的 OAuth 授权（见 SKILL.md 连接流程）。"""
    prefix = _python_argv()
    return _run_cli([*prefix, str(_SKILL_SCRIPTS / "authorize.py")])


def _beatra_upload(path: str, mime_type: str) -> str:
    """安全上传一个本地媒体文件并返回素材引用。"""
    if not (path or "").strip():
        raise ToolError("缺少 path：要上传的本地文件路径")
    if not (mime_type or "").strip():
        raise ToolError("缺少 mime_type：文件的 MIME 类型，例如 image/png")
    args = ["upload", str(path), "--mime-type", str(mime_type)]
    prefix = _python_argv()
    return _run_cli([*prefix, str(_MCP_CLIENT), *args])


def build_beatra_tools() -> List[ToolSpec]:
    """构建 beatra 相关工具声明（call / authorize / upload）。"""
    return [
        ToolSpec(
            name="beatra_call",
            description=(
                "调用已安装的 beatra Skill 的 MCP 工具，完成 AI图片/视频/音乐/语音创作、"
                "视频编辑与公开社交数据查找等操作。参数以 JSON 对象通过标准输入传入，"
                "不要在其中写入本地路径或凭据。常用工具：beatra.images.generate、"
                "beatra.videos.generate、beatra.music.generate、beatra.speech.synthesize、"
                "beatra.social.tools.search 等。创建/查找细节、计费边界与授权流程必须先读 "
                "skills/beatra/SKILL.md 及其 references/ 文档。返回退出码、stdout 与 stderr。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "tool": {
                        "type": "string",
                        "description": "要调用的 Beatra MCP 工具名，例如 beatra.tasks.list",
                    },
                    "arguments_json": {
                        "type": "string",
                        "description": "传给该工具的 JSON 对象（字符串形式），默认 '{}'",
                    },
                },
                "required": ["tool"],
            },
            handler=_beatra_call,
        ),
        ToolSpec(
            name="beatra_authorize",
            description=(
                "发起或恢复 beatra Skill 的设备授权（OAuth Device Flow）：会打印批准链接，"
                "用户打开链接登录/注册并点「允许」，授权完成会输出 'Beatra is ready'。"
                "首次使用或连接失效时运行。返回退出码（3 表示仍等待批准）与输出。"
            ),
            parameters={"type": "object", "properties": {}, "required": []},
            handler=_beatra_authorize,
        ),
        ToolSpec(
            name="beatra_upload",
            description=(
                "安全上传一个本地媒体文件（图片/视频/音频）到 Beatra，返回素材引用。"
                "遵守 100 MB 上限。把本地路径与 MIME 类型传入，例如 path=\"C:/a.png\" "
                "mime_type=\"image/png\"。不要手动发送字节或路径给生成工具。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要上传的本地文件路径",
                    },
                    "mime_type": {
                        "type": "string",
                        "description": "文件的 MIME 类型，例如 image/png、video/mp4、audio/mpeg",
                    },
                },
                "required": ["path", "mime_type"],
            },
            handler=_beatra_upload,
        ),
    ]
