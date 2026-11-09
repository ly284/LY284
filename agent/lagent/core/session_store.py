"""会话持久化：把对话历史保存到本地 `.agents/sessions/` 并支持列举、恢复。

每个会话一个 JSONL 文件（每行一条 OpenAI 协议消息），文件名即会话编号，
形如 ``20261022-153000.jsonl``。标题取自第一条 user 消息，便于 /resume 列表展示。
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

__all__ = [
    "SessionInfo",
    "SessionStore",
    "DEFAULT_SESSIONS_DIR",
]

# 默认会话目录（相对项目根目录）
DEFAULT_SESSIONS_DIR = ".agents/sessions"

# 标题截断长度
TITLE_CHARS = 36


def _clip_title(text: Optional[str]) -> str:
    text = (text or "").strip()
    if not text:
        return "(无标题)"
    folded = " ".join(text.splitlines())
    if len(folded) <= TITLE_CHARS:
        return folded
    return folded[:TITLE_CHARS] + "…"


@dataclass(frozen=True)
class SessionInfo:
    """已保存会话的摘要信息。"""

    session_id: str
    title: str
    message_count: int
    saved_at: str
    path: str


class SessionStore:
    """管理 `.agents/sessions/` 目录：保存 / 列举 / 恢复会话。"""

    def __init__(self, directory: Optional[str] = None) -> None:
        self._dir = Path(directory or DEFAULT_SESSIONS_DIR)
        if not self._dir.is_absolute():
            self._dir = Path(os.getcwd()) / self._dir

    @property
    def directory(self) -> str:
        return str(self._dir)

    def new_id(self) -> str:
        """生成唯一会话编号；同秒冲突时追加后缀避免覆盖。"""
        base = datetime.now().strftime("%Y%m%d-%H%M%S")
        if not (self._dir / f"{base}.jsonl").exists():
            return base
        n = 1
        while (self._dir / f"{base}-{n}.jsonl").exists():
            n += 1
        return f"{base}-{n}"

    def save(self, messages: Sequence[Dict[str, Any]], session_id: Optional[str] = None) -> SessionInfo:
        """把消息列表保存为会话文件，返回摘要信息。"""
        session_id = session_id or self.new_id()
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{session_id}.jsonl"
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            for message in messages:
                fh.write(json.dumps(message, ensure_ascii=False) + "\n")

        title = _clip_title(_first_user_text(messages))
        return SessionInfo(
            session_id=session_id,
            title=title,
            message_count=len(messages),
            saved_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            path=str(path),
        )

    def list_sessions(self, limit: int = 50) -> List[SessionInfo]:
        """按保存时间倒序列举最近会话（最多 limit 个）。"""
        if not self._dir.is_dir():
            return []
        files = sorted(self._dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        out: List[SessionInfo] = []
        for path in files[:limit]:
            session_id = path.stem
            messages = self._read_messages(path)
            title = _clip_title(_first_user_text(messages))
            try:
                saved_at = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            except OSError:
                saved_at = ""
            out.append(
                SessionInfo(
                    session_id=session_id,
                    title=title,
                    message_count=len(messages),
                    saved_at=saved_at,
                    path=str(path),
                )
            )
        return out

    def load(self, session_id: str) -> Optional[List[Dict[str, Any]]]:
        """读取指定会话的消息列表；不存在时返回 None。"""
        name = session_id.strip()
        if name.lower().endswith(".jsonl"):
            name = name[:-6]
        path = self._dir / f"{name}.jsonl"
        if not path.is_file():
            return None
        return self._read_messages(path)

    @staticmethod
    def _read_messages(path: Path) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        messages.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return []
        return messages


def _first_user_text(messages: Sequence[Dict[str, Any]]) -> str:
    for message in messages:
        if message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content
    return ""