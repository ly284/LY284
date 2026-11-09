"""上下文管理：Token 估算、历史归档、上下文压缩与检索。

功能组成：
- Token 估算：优先使用模型 API 返回的真实 Token 使用量；拿不到时用
  字符级近似估算（中文按 1 字 ≈ 1 Token，其它字符约 4 字 ≈ 1 Token）。
- ContextArchiver：把压缩前的原始上下文完整保存到项目本地
  `.agents/context/` 目录（每行一条 JSON 消息），并支持本地全文检索。
- 上下文压缩 Prompt：用于生成约 5,000 Tokens 的工作摘要。
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

__all__ = [
    "DEFAULT_CONTEXT_WINDOW",
    "CONTEXT_DIR_NAME",
    "COMPRESSION_SYSTEM_PROMPT",
    "estimate_text_tokens",
    "estimate_message_tokens",
    "estimate_usage",
    "format_transcript",
    "ContextArchiver",
]

# 无法获取模型真实上下文窗口时的默认值（128k）
DEFAULT_CONTEXT_WINDOW = 128_000

# 归档目录相对项目根目录的默认名
CONTEXT_DIR_NAME = ".agents/context"

# 压缩时限制生成摘要的最大 Tokens（提示为约 5,000 Tokens）
DEFAULT_COMPRESS_MAX_TOKENS = 6_000

# recallContext 检索结果长度控制
MAX_RECALL_RESULTS = 8       # 最多返回的片段条数
RECALL_SNIPPET_CHARS = 260   # 每个片段截断长度
RECALL_CONTENT_CHARS = 5_000 # 检索结果总字符上限


# ---------------------------------------------------------------------------
# Token 估算
# ---------------------------------------------------------------------------

# 中日韩统一表意文字等视为“一个字 ≈ 1 Token”的粗略区间
_CJK_RE = re.compile(
    r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef\uac00-\ud7af\u3040-\u30ff]"
)


def estimate_text_tokens(text: str) -> int:
    """对一段文本做粗略 Token 估算（非精确，仅供监控使用）。"""
    if not text:
        return 0
    cjk = len(_CJK_RE.findall(text))
    ascii_len = len(text) - cjk
    return cjk + max(1, round(ascii_len / 4)) + 1


def estimate_message_tokens(message: Dict[str, Any]) -> int:
    """估算一条 OpenAI 协议消息占用的 Tokens（含角色、结构开销）。"""
    tokens = 4
    for value in message.values():
        if isinstance(value, str):
            tokens += estimate_text_tokens(value)
        elif isinstance(value, list):  # tool_calls 等结构
            tokens += estimate_text_tokens(json.dumps(value, ensure_ascii=False))
    return tokens


def estimate_usage(
    messages: Sequence[Dict[str, Any]],
    tool_defs: Optional[Sequence[Dict[str, Any]]] = None,
) -> int:
    """估算整段会话（系统提示 + 对话历史 + 工具声明）占用的 Tokens。"""
    total = sum(estimate_message_tokens(m) for m in messages)
    if tool_defs:
        total += estimate_text_tokens(json.dumps(list(tool_defs), ensure_ascii=False))
    return total


# ---------------------------------------------------------------------------
# 转录：把消息列表转成可读文本（用于压缩输入与界面预览）
# ---------------------------------------------------------------------------

_ROLE_LABELS = {
    "system": "System",
    "user": "User",
    "assistant": "Assistant",
    "tool": "Tool",
}


def format_transcript(messages: Sequence[Dict[str, Any]]) -> str:
    """把 OpenAI 协议消息列表整理成逐条可读文本。

    保留角色、内容、工具调用参数与工具返回结果、消息顺序，供
    上下文压缩与前端压缩面板展示使用。
    """
    blocks: List[str] = []
    for idx, message in enumerate(messages, start=1):
        role = message.get("role") or ""
        lines = [f"[{idx}] {_ROLE_LABELS.get(role, role)}"]
        content = message.get("content")
        if role == "tool":
            lines.append(f"tool_call_id: {message.get('tool_call_id') or ''}")
        if content:
            lines.append(str(content))
        for tc in message.get("tool_calls") or []:
            fn = tc.get("function") or {}
            lines.append(
                f"→ tool_call: {fn.get('name') or ''} "
                f"{fn.get('arguments') or '{}'}"
            )
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# 上下文压缩专用 Prompt
# ---------------------------------------------------------------------------

COMPRESSION_SYSTEM_PROMPT = """你是一名 AI Agent 的上下文管理助手。当前会话即将达到上下文窗口限制，需要将历史对话压缩为一份高质量的工作摘要，以便 Agent 在新的上下文中继续执行任务。

请认真阅读提供的历史上下文，提取对后续工作仍然有价值的信息，并生成一份约 5,000 Tokens 的 Markdown 摘要。

摘要应重点保留以下内容：

1. **用户目标与要求**：用户希望完成什么任务？有哪些必须遵守的约束、偏好和验收条件？
2. **已经完成的工作**：哪些任务已经完成？实现了哪些功能？获得了哪些已经验证的结果？
3. **当前工作状态**：Agent 正在处理什么任务？当前进展到哪一步？是否存在尚未解决的问题？
4. **关键技术信息**：保留重要的文件路径、函数名称、接口定义、配置项、执行命令、错误信息和必要的代码片段。
5. **关键决策与原因**：记录用户和 Agent 已经确定的技术方案，以及重要的设计取舍。
6. **下一步任务**：明确接下来应该执行的操作，以及需要继续验证的事项。

请遵守以下要求：

- 优先保留对后续任务有直接影响的信息，删除寒暄、重复讨论、过时的尝试和无关内容。
- 对已经验证的事实与尚未验证的推测作出明确区分。
- 不要将计划完成的任务描述为已经完成。
- 重要的文件路径、函数名称、配置名称和命令应保留准确原文。
- 对失败的尝试，只保留有助于避免重复错误的信息。
- 如果信息存在冲突，应优先保留用户最新确认的要求，并简要说明仍然存在的冲突。
- 如果某些历史细节无法在摘要中完整保留，可简要说明它们已保存到原始上下文归档中，后续可以通过 `recallContext` 工具重新检索。
- 使用清晰的 Markdown 结构输出摘要，不要附加解释或无关内容。

最终目标：使一个从未阅读过原始对话的 Agent，仅凭这份摘要，就能够理解当前任务、继承关键决策，并继续开展工作。"""


# ---------------------------------------------------------------------------
# 历史归档与检索
# ---------------------------------------------------------------------------


def _message_for_search(message: Dict[str, Any]) -> str:
    """把一条消息转成可供全文匹配的文本（角色 + 内容 + 工具信息）。"""
    parts: List[str] = []
    role = message.get("role") or ""
    parts.append(role)
    content = message.get("content")
    if content:
        parts.append(content if isinstance(content, str) else json.dumps(content, ensure_ascii=False))
    for tc in message.get("tool_calls") or []:
        fn = tc.get("function") or {}
        parts.append(fn.get("name") or "")
        parts.append(fn.get("arguments") or "{}")
    if message.get("tool_call_id"):
        parts.append(str(message["tool_call_id"]))
    return "\n".join(parts)


def _clip_snippet(content: Any, limit: int = RECALL_SNIPPET_CHARS) -> str:
    text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + f"…（片段已截断，共 {len(text)} 字）"


class ContextArchiver:
    """管理 `.agents/context/` 目录：保存原始上下文 JSONL 并支持检索。"""

    def __init__(self, directory: Optional[str] = None) -> None:
        self._dir = Path(directory or CONTEXT_DIR_NAME)
        if not self._dir.is_absolute():
            self._dir = Path(os.getcwd()) / self._dir

    @property
    def directory(self) -> str:
        return str(self._dir)

    def new_id(self) -> str:
        """生成唯一归档编号，形如 20261022-153000；同秒冲突时追加后缀。"""
        base = datetime.now().strftime("%Y%m%d-%H%M%S")
        if not (self._dir / f"{base}.jsonl").exists():
            return base
        n = 1
        while (self._dir / f"{base}-{n}.jsonl").exists():
            n += 1
        return f"{base}-{n}"

    def save(self, messages: Sequence[Dict[str, Any]], archive_id: Optional[str] = None) -> str:
        """把消息列表原样写入归档文件（每行一条 JSON），返回文件路径。

        逐条保留 role / content / tool_calls / tool_call_id 与消息顺序。
        """
        archive_id = archive_id or self.new_id()
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{archive_id}.jsonl"
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            for message in messages:
                fh.write(json.dumps(message, ensure_ascii=False) + "\n")
        return str(path)

    def list_archives(self) -> List[Path]:
        """返回全部归档文件（按文件名排序）。"""
        if not self._dir.is_dir():
            return []
        return sorted(self._dir.glob("*.jsonl"))

    def _pick_archives(self, archive_id: Optional[str] = None) -> List[Path]:
        if archive_id:
            name = archive_id.strip()
            if name.lower().endswith(".jsonl"):
                name = name[:-6]
            path = self._dir / f"{name}.jsonl"
            return [path] if path.is_file() else []
        return self.list_archives()

    def search(
        self,
        text: str,
        archive_id: Optional[str] = None,
        *,
        max_results: int = MAX_RECALL_RESULTS,
        char_limit: int = RECALL_CONTENT_CHARS,
    ) -> str:
        """在指定（或全部）归档中做本地全文关键词检索。

        支持多关键词（以空白分隔，需同时命中）。返回匹配的内容片段、
        归档编号与所在行号；命中过多时按片段截断、控制总长度。
        """
        text = (text or "").strip()
        if not text:
            return "recallContext 工具参数错误：text（要查找的关键词）不能为空"

        keywords = [word.lower() for word in text.split() if word.strip()]
        if not keywords:
            keywords = [text.lower()]

        files = self._pick_archives(archive_id)
        if not files:
            if archive_id:
                return f"未找到编号为 {archive_id} 的上下文归档"
            return f"目录 {self.directory} 下还没有任何上下文归档"

        hits: List[tuple] = []
        for path in files:
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    lines = fh.readlines()
            except OSError as exc:
                continue
            for lineno, line in enumerate(lines, start=1):
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                blob = _message_for_search(message).lower()
                if all(keyword in blob for keyword in keywords):
                    hits.append((path, lineno, message))

        if not hits:
            if archive_id:
                return f"归档 {archive_id} 中未找到包含 “{text}”的内容"
            return f"全部 {len(files)} 个历史归档中未找到包含 “{text}”的内容"

        total = len(hits)
        shown = min(total, max_results)
        out = [
            f"共命中 {total} 条片段（显示前 {shown} 条）。来源: "
            f"{'编号 '+str(archive_id) if archive_id else f'{len(files)} 个归档文件'}："
        ]
        used = 0
        for i, (path, lineno, message) in enumerate(hits[:shown], start=1):
            role = message.get("role") or ""
            snippet = _clip_snippet(message.get("content"))
            block = (
                f"\n[匹配 {i}] 归档 {path.stem} · 行 {lineno} · 角色 {role}\n"
                f"文件位置: {path}\n"
                f"{snippet}\n"
            )
            if used + len(block) > char_limit:
                out.append(f"\n…（检索结果过长，已截断，其余片段请缩小关键词范围）")
                break
            used += len(block)
            out.append(block)
        return "\n".join(out)