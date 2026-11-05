"""创建 Agent Skills 工具：根据用户自然语言要求生成新的 Skill。

在“当前项目的 .agents/skills/”目录下创建与 name 对应的英文子目录，并写入
符合 Agent Skills 规范的 SKILL.md（含 YAML Frontmatter 的 name / description
与正文）。若同名 Skill 已存在则明确拒绝，避免意外覆盖。
"""

from __future__ import annotations

import os
import re

from .base import ToolSpec, ToolError

__all__ = ["build_create_skill_tool", "create_skill"]


# Skill 名称：小写字母、数字与连字符。仅使用这些字符，可避免非法目录名。
_SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# 默认技能目录名（Agent Skills 惯例）
_DEFAULT_SKILLS_DIR = ".agents/skills"


def _parse_skill_context(context: str):
    """从 SKILL.md 全文提取 YAML Frontmatter 中的 name / description。

    返回 (name, description)。用于校验写入内容符合 Agent Skills 规范：
    - 首行须为 ``---``，其后再有一个 ``---`` 闭合 Frontmatter；
    - 必须具备 name 与 description 字段，description 可多行续行。
    不满足时抛出 ToolError。
    """
    if not context or not context.strip():
        raise ToolError("skillContext 内容为空，无法创建 Skill")
    lines = context.splitlines()
    if lines[0].strip() != "---":
        raise ToolError("skillContext 必须以一行 '---' 开头（YAML Frontmatter 起始）")
    fields: dict = {}
    current: str | None = None
    closed = False
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            closed = True
            break
        match = re.match(r"^\s*([A-Za-z0-9_-]+)\s*:\s*(.*)$", line)
        if match:
            key, value = match.group(1).lower(), match.group(2).strip()
            if value:
                fields[key] = value.strip("\"'")
            current = key
        elif current in ("name", "description") and current in fields:
            fields[current] = (fields[current] + " " + stripped).strip()
    if not closed:
        raise ToolError("skillContext 缺少 YAML Frontmatter 结束标记（第二个 '---'）")
    name = fields.get("name", "").strip()
    description = fields.get("description", "").strip()
    if not name:
        raise ToolError("skillContext 的 Frontmatter 缺少 name 字段")
    if not description:
        raise ToolError("skillContext 的 Frontmatter 缺少 description 字段")
    return name, description


def create_skill(name: str, skillContext: str) -> str:
    """根据名称与 SKILL.md 内容创建 Skill；已存在时返回明确提示，不覆盖。"""
    if not name or not name.strip():
        raise ToolError("缺少 name 参数")
    name = name.strip().lower()
    if not _SKILL_NAME_RE.match(name):
        raise ToolError(
            f"非法 Skill 名称: {name!r}。名称只能使用小写字母、数字与连字符，"
            "且须以字母或数字开头"
        )

    # 校验 skillContext 符合 Agent Skills 规范
    fm_name, fm_description = _parse_skill_context(skillContext)
    if fm_name != name:
        raise ToolError(
            f"skillContext Frontmatter 中的 name（{fm_name!r}）与参数 name "
            f"（{name!r}）不一致"
        )

    skills_root = os.path.join(os.getcwd(), _DEFAULT_SKILLS_DIR)
    skill_dir = os.path.join(skills_root, name)
    skill_md = os.path.join(skill_dir, "SKILL.md")
    if os.path.isdir(skill_dir):
        return (
            f"Skill `{name}` 已存在（{os.path.abspath(skill_dir)}），为避免覆盖原有内容"
            "，未做任何修改。如需更新，请先删除后再创建。"
        )

    os.makedirs(skill_dir)
    try:
        with open(skill_md, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(skillContext)
    except OSError as exc:
        raise ToolError(f"写入 SKILL.md 失败: {exc}") from exc
    return (
        f"已成功创建新 Skill `{name}`。\n"
        f"目录: {os.path.abspath(skill_dir)}\n"
        f"描述: {fm_description}\n"
        f"如需补充 references/、scripts/ 等目录或辅助文件，请继续调用 fileOps 相关工具完成。"
    )


def build_create_skill_tool() -> ToolSpec:
    """构建 createskill 工具声明。"""
    return ToolSpec(
        name="createskill",
        description=(
            "创建新的 Agent Skill。根据用户对某个技能的描述生成一个符合 Agent Skills "
            "规范的 Skill：在当前项目的 .agents/skills/ 目录下新建以 name 命名的子目录，"
            "并把 skillContext 作为 SKILL.md 写入其中。name 使用小写字母、数字与连字符。"
            "skillContext 必须是完整的 SKILL.md 内容，开头需包含 YAML Frontmatter "
            "（--- 包围，含 name 与 description 字段）及随后的正文。若同名 Skill 已存在，"
            "会返回提示且不会覆盖。创建后如需额外的 references/、scripts/ 等目录或辅助文件，"
            "继续调用 fileOps 相关工具完成。"
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "name": {
                    "type": "string",
                    "description": (
                        "新 Skill 的名称，仅支持小写字母、数字与连字符，须以小写字母或数字开头。"
                        "将用作 .agents/skills/ 下的子目录名并写入 SKILL.md Frontmatter 的 name。"
                    ),
                },
                "skillContext": {
                    "type": "string",
                    "description": (
                        "需要写入 SKILL.md 的完整内容：以 --- 开头的 YAML Frontmatter"
                        "（含 name 与 description 字段，description 需对技能用途给出充分描述）"
                        "，其后是正文说明。"
                    ),
                },
            },
            "required": ["name", "skillContext"],
        },
        handler=create_skill,
    )
