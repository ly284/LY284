"""系统工具：日期时间查询、闰年判断。"""

from __future__ import annotations

import locale
import os
import subprocess
from typing import List

from .base import ToolSpec

__all__ = ["SYSTEM_TOOLS"]


def _decode_cmd(data: bytes) -> str:
    """按顺序尝试解码，兼容 Windows GBK 控制台与 UTF-8 输出。"""
    for enc in ("utf-8", locale.getpreferredencoding(False), "gbk"):
        if not enc:
            continue
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def getdate() -> str:
    """调用本机 date 命令获取日期和时间。"""
    if os.name == "nt":
        # Windows：date 命令不加 /t 会等待输入，用 /t 直接输出
        cmd = ["cmd", "/c", "date /t & time /t"]
    else:
        # Linux / macOS：stdin 传空避免挂起
        cmd = ["date"]
    proc = subprocess.run(cmd, input=b"", capture_output=True, timeout=10)
    text = _decode_cmd(proc.stdout).strip() or _decode_cmd(proc.stderr).strip()
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def isleapyear(year: int) -> str:
    """判断某年是否为闰年。"""
    y = int(year)
    leap = (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)
    return f"{y}年{'是' if leap else '不是'}闰年"


SYSTEM_TOOLS: List[ToolSpec] = [
    ToolSpec(
        name="getdate",
        description="获取当前电脑的日期和时间，通过调用系统 date 命令得到",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=getdate,
    ),
    ToolSpec(
        name="isleapyear",
        description="计算某一年是否是闰年",
        parameters={
            "type": "object",
            "properties": {
                "year": {
                    "type": "integer",
                    "description": "要判断的年份，例如 2024",
                },
            },
            "required": ["year"],
        },
        handler=isleapyear,
    ),
]
