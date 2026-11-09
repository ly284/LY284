"""recallContext 工具：检索历史上下文归档（本地全文关键词检索）。

归档由 ContextArchiver 写入 `.agents/context/`（每行一条 JSON 消息）。
该工具让模型在压缩后的会话中，按需找回原始上下文中的细节。
"""

from __future__ import annotations

from typing import Optional

from .base import ToolSpec
from ..context import ContextArchiver

__all__ = ["build_recall_context_tool"]


def build_recall_context_tool(archiver: ContextArchiver) -> ToolSpec:
    """构造 recallContext 工具声明，绑定给定归档器。"""

    def handler(id: Optional[str] = None, text: str = "") -> str:
        try:
            return archiver.search(text=text, archive_id=id)
        except Exception as exc:  # noqa: BLE001 - 错误以文本回传模型处理
            return f"工具执行失败: recallContext 检索失败（{type(exc).__name__}: {exc}）"

    return ToolSpec(
        name="recallContext",
        description=(
            "检索此前压缩时保存的历史上下文归档（存于项目 .agents/context/ 目录）。"
            "当当前会话（压缩摘要）缺少某些历史细节，如文件路径、函数名、配置项、"
            "验证过的实验结果或用户要求时，传入关键词 text 进行全文检索；可选传入 id "
            "（归档编号，形如 20261022-153000）限定在某个归档内检索，不传则检索全部归档。"
            "返回匹配的原始内容片段、归档编号与所在行号。"
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "id": {
                    "type": "string",
                    "description": "可选的归档编号（例如 20261022-153000）；省略时检索全部历史归档",
                },
                "text": {
                    "type": "string",
                    "description": (
                        "需要查找的关键词或文本内容；支持多个关键词（用空格分隔，"
                        "需同时命中）。返回匹配的原始内容片段、归档编号与位置。"
                    ),
                },
            },
            "required": ["text"],
        },
        handler=handler,
    )