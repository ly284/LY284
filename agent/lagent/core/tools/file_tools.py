"""本地文件操作工具：目录/文件的增删改查与重命名。"""

from __future__ import annotations

import mimetypes
import os
import shutil
from typing import List

from .base import ToolSpec, ToolError

__all__ = ["FILE_TOOLS"]


def _decode_text(data: bytes, path: str) -> str:
    """按 UTF-8 / GBK 顺序尝试解码纯文本字节，出现二进制特征直接报错。"""
    if b"\x00" in data:
        raise ToolError(f"检测到二进制内容，仅支持纯文本文件: {path}")
    for enc in ("utf-8", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ToolError(f"无法以 UTF-8 / GBK 解码，可能是二进制文件: {path}")


def _read_text(path: str) -> str:
    if os.path.isdir(path):
        raise ToolError(f"这是目录，不是文件: {path}")
    if not os.path.isfile(path):
        raise ToolError(f"文件不存在: {path}")
    with open(path, "rb") as f:
        return _decode_text(f.read(), path)


def getcwd() -> str:
    return os.getcwd()


def list_dir(path: str = ".") -> str:
    if not os.path.isdir(path):
        raise ToolError(f"目录不存在: {path}")
    items = []
    with os.scandir(path) as it:
        for entry in it:
            kind = "目录" if entry.is_dir() else "文件"
            size = "" if entry.is_dir() else f"，{entry.stat().st_size} 字节"
            items.append(f"[{kind}] {entry.name}{size}")
    if not items:
        return f"目录 {os.path.abspath(path)} 为空"
    return f"目录 {os.path.abspath(path)} 共 {len(items)} 项:\n" + "\n".join(items)


def get_file_type(path: str) -> str:
    if not os.path.exists(path):
        raise ToolError(f"路径不存在: {path}")
    if os.path.isdir(path):
        return f"{path} 是目录"
    mime, _ = mimetypes.guess_type(path)
    ext = os.path.splitext(path)[1] or "(无扩展名)"
    return f"{path} 是文件，扩展名 {ext}，MIME 类型 {mime or '未知'}"


def read_text_file(path: str) -> str:
    return f"{path} 内容如下:\n{_read_text(path)}"


def create_file(path: str, content: str = "", overwrite: bool = False) -> str:
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    if os.path.exists(path) and not overwrite:
        raise ToolError(f"文件已存在: {path}，如需覆盖请设置 overwrite")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content or "")
    return f"已创建文件: {os.path.abspath(path)}"


def edit_file(path: str, content: str = "", mode: str = "append") -> str:
    if mode == "append":
        with open(path, "a", encoding="utf-8", newline="\n") as f:
            f.write(content or "")
    elif mode == "prepend":
        old = _read_text(path)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write((content or "") + old)
    elif mode == "replace":
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content or "")
    else:
        raise ToolError(f"不支持的模式: {mode}，可选 append / prepend / replace")
    return f"已用 {mode} 模式更新文件: {path}"


def create_directory(path: str) -> str:
    if os.path.isdir(path):
        return f"目录已存在: {os.path.abspath(path)}"
    os.makedirs(path)
    return f"已创建目录: {os.path.abspath(path)}"


def remove_directory(path: str) -> str:
    if not os.path.isdir(path):
        raise ToolError(f"目录不存在: {path}")
    shutil.rmtree(path)
    return f"已删除目录及其全部内容: {path}"


def delete_file(path: str) -> str:
    if os.path.isdir(path):
        raise ToolError(f"这是目录，请改用删除目录工具: {path}")
    if not os.path.isfile(path):
        raise ToolError(f"文件不存在: {path}")
    os.remove(path)
    return f"已删除文件: {path}"


def rename_path(src: str, dst: str) -> str:
    if not os.path.exists(src):
        raise ToolError(f"源路径不存在: {src}")
    if os.path.exists(dst):
        raise ToolError(f"目标路径已存在: {dst}")
    parent = os.path.dirname(os.path.abspath(dst))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    shutil.move(src, dst)
    return f"已将 {src} 重命名为 {dst}"


def _path_prop(description: str) -> dict:
    return {"type": "string", "description": description}


FILE_TOOLS: List[ToolSpec] = [
    ToolSpec(
        name="getcwd",
        description="获取当前工作目录的完整路径",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=getcwd,
    ),
    ToolSpec(
        name="list_dir",
        description="列出指定目录下的所有文件和子目录，不填 path 时列出当前目录",
        parameters={
            "type": "object",
            "properties": {
                "path": _path_prop("要列出的目录路径，例如 D:/test 或相对路径 ."),
            },
            "required": [],
        },
        handler=list_dir,
    ),
    ToolSpec(
        name="get_file_type",
        description="获取指定文件的文件类型（扩展名与 MIME 类型），目录会单独说明",
        parameters={
            "type": "object",
            "properties": {"path": _path_prop("要判断类型的文件路径")},
            "required": ["path"],
        },
        handler=get_file_type,
    ),
    ToolSpec(
        name="read_text_file",
        description="读取指定纯文本文件的内容，二进制文件会拒绝读取",
        parameters={
            "type": "object",
            "properties": {"path": _path_prop("要读取的纯文本文件路径")},
            "required": ["path"],
        },
        handler=read_text_file,
    ),
    ToolSpec(
        name="create_file",
        description="根据目录和文件名创建新文件，父目录不存在时会一并创建",
        parameters={
            "type": "object",
            "properties": {
                "path": _path_prop("要创建的文件完整路径，例如 D:/test/a.txt"),
                "content": {"type": "string", "description": "写入文件的文本内容，默认空字符串"},
                "overwrite": {"type": "boolean", "description": "文件已存在时是否覆盖，默认 false"},
            },
            "required": ["path"],
        },
        handler=create_file,
    ),
    ToolSpec(
        name="edit_file",
        description="编辑指定纯文本文件的内容，支持追加、前置、整体替换",
        parameters={
            "type": "object",
            "properties": {
                "path": _path_prop("要编辑的纯文本文件路径"),
                "content": {"type": "string", "description": "要写入的文本内容"},
                "mode": {
                    "type": "string",
                    "enum": ["append", "prepend", "replace"],
                    "description": "编辑模式：append 追加到末尾，prepend 插入到开头，replace 整体替换，默认 append",
                },
            },
            "required": ["path", "content"],
        },
        handler=edit_file,
    ),
    ToolSpec(
        name="create_directory",
        description="创建新目录，父目录不存在时会一并创建",
        parameters={
            "type": "object",
            "properties": {"path": _path_prop("要创建的目录路径")},
            "required": ["path"],
        },
        handler=create_directory,
    ),
    ToolSpec(
        name="remove_directory",
        description="删除指定目录及其全部内容，非空目录也能删除",
        parameters={
            "type": "object",
            "properties": {"path": _path_prop("要删除的目录路径")},
            "required": ["path"],
        },
        handler=remove_directory,
    ),
    ToolSpec(
        name="delete_file",
        description="删除指定文件",
        parameters={
            "type": "object",
            "properties": {"path": _path_prop("要删除的文件路径")},
            "required": ["path"],
        },
        handler=delete_file,
    ),
    ToolSpec(
        name="rename_path",
        description="重命名或移动文件、目录",
        parameters={
            "type": "object",
            "properties": {
                "src": _path_prop("原文件或目录路径"),
                "dst": _path_prop("新的文件或目录路径"),
            },
            "required": ["src", "dst"],
        },
        handler=rename_path,
    ),
]
