"""Skill 发现、登记与按需加载。

Skill 子目录需包含一个 SKILL.md，其开头通过 YAML Frontmatter 声明：
- name: 技能唯一名称（必需）
- description: 技能用途说明（必需）

初始化阶段只会解析这两项；SKILL.md 全文与附件文件均在模型调用
loadSkill 工具时才读取，避免占用对话上下文。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ..tools.base import ToolError, ToolSpec


def resolve_skills_root(project_root: str, skills_dir: str = "") -> Optional[str]:
    """在项目根目录定位技能目录。

    优先级：显式 skills_dir > <project_root>/.agents/skills > <project_root>/skills。
    返回第一个存在的目录；若都不存在返回 None。
    """
    if skills_dir:
        if os.path.isdir(skills_dir):
            return os.path.abspath(skills_dir)
        return None
    for name in (".agents/skills", "skills"):
        candidate = os.path.join(project_root, name)
        if os.path.isdir(candidate):
            return candidate
    return None


# 匹配 YAML Frontmatter 中的 ``name: 值`` 行（允许单/双引号包裹）
_KEY_LINE = re.compile(r"^\s*([A-Za-z0-9_-]+)\s*:\s*(.*)$")


@dataclass(frozen=True)
class SkillInfo:
    """Skills 目录中某个 Skill 的名称、描述及其子目录路径。"""

    name: str
    description: str
    directory: str


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _parse_frontmatter(skill_md: str) -> Dict[str, str]:
    """解析 SKILL.md 开头 YAML Frontmatter，仅提取 name / description。

    Frontmatter 由首行 ``---`` 与下一行 ``---`` 包围。description 支持
    多行（缩进续行）与引号包裹。
    """
    lines = skill_md.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields: Dict[str, str] = {}
    current: Optional[str] = None
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            break
        match = _KEY_LINE.match(line)
        if match:
            key, value = match.group(1).lower(), match.group(2)
            if not value and current == key:
                continue
            fields[key] = _strip_quotes(value)
            current = key
        elif current and current in ("name", "description"):
            # 缩进续行，追加到当前字段
            fields[current] = (fields[current] + " " + line.strip()).strip()
    return fields


def discover_skills(skills_root: str) -> List[SkillInfo]:
    """扫描 skills_root 之下每个子目录的 SKILL.md，登记 name / description。"""
    if not skills_root or not os.path.isdir(skills_root):
        return []
    out: List[SkillInfo] = []
    seen: set = set()
    with os.scandir(skills_root) as it:
        for entry in it:
            if not entry.is_dir():
                continue
            skill_dir = entry.path
            skill_md = os.path.join(skill_dir, "SKILL.md")
            if not os.path.isfile(skill_md):
                continue
            try:
                with open(skill_md, "r", encoding="utf-8") as fh:
                    fields = _parse_frontmatter(fh.read())
            except OSError:
                continue
            name = (fields.get("name") or "").strip()
            description = (fields.get("description") or "").strip()
            if not name or not description:
                continue
            if name in seen:
                continue
            seen.add(name)
            out.append(SkillInfo(name=name, description=description, directory=skill_dir))
    return out


def _is_within(base: str, target: str) -> bool:
    base_real = os.path.realpath(base)
    target_real = os.path.realpath(target)
    return target_real == base_real or target_real.startswith(base_real + os.sep)


# 按需加载时的内容长度上限：超出截断并标明，防止一次调用占满上下文
MAX_SKILL_CONTENT_CHARS = 20_000


def _clip_content(text: str) -> str:
    if len(text) <= MAX_SKILL_CONTENT_CHARS:
        return text
    head = text[:MAX_SKILL_CONTENT_CHARS]
    return (
        f"{head}\n\n...[内容过长，已截断，共 {len(text)} 字符，"
        f"仅保留前 {MAX_SKILL_CONTENT_CHARS} 字符；可用 filename 参数分段读取附件文件]..."
    )


class SkillManager:
    """管理已发现 Skill 的注册表与按需加载。"""

    def __init__(self, project_root: Optional[str] = None, skills_dir: str = "") -> None:
        self._project_root = os.path.abspath(project_root or os.getcwd())
        self._skills_dir = resolve_skills_root(self._project_root, skills_dir)
        self._skills: Dict[str, SkillInfo] = {
            skill.name: skill for skill in discover_skills(self._skills_dir)
        }

    @property
    def skills(self) -> Dict[str, SkillInfo]:
        return dict(self._skills)

    @property
    def enabled(self) -> bool:
        return bool(self._skills)

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """兼容层：无实际作用，保持 create_agent 组装方式统一。"""

    def inject_prompt(self) -> str:
        """生成注入 System Prompt 的可用技能清单（无技能时返回空串）。"""
        if not self._skills:
            return ""
        lines = [
            "You have access to the following skills:",
        ]
        for skill in self._skills.values():
            lines.append(f"- `{skill.name}`: {skill.description}")
        lines.extend(
            [
                "Use the loadSkill tool to load the full instructions of a skill "
                "when needed. You can also load additional files referenced by a "
                "skill by passing the filename argument.",
            ]
        )
        return "\n".join(lines)

    # ---------- 按需加载 ----------

    def _resolve_file(self, skill: SkillInfo, filename: str) -> Tuple[Optional[str], Optional[str]]:
        """把文件名解析成 Skill 目录内的目标文件路径。

        返回 (目标路径, 候选提示)。二者有且仅有一个不为 None：
        - 精确命中 / 唯一命中时返回 (path, None)；
        - 多个同名文件时返回 (None, 候选路径提示)，交由模型决定。

        优先做精确路径匹配（相对 Skill 目录、项目根目录、绝对路径）；
        匹配不到再按文件名递归搜索 Skill 目录。读取范围始终限定在 Skill 目录内。
        """
        if not filename or not filename.strip():
            raise ToolError("缺少 filename 参数")
        filename = filename.strip()
        skill_dir_real = os.path.realpath(skill.directory)

        # 1) 绝对路径
        if os.path.isabs(filename):
            target = os.path.realpath(filename)
            if not _is_within(skill_dir_real, target):
                raise ToolError(f"文件超出 Skill 目录范围，禁止读取: {filename}")
            if os.path.isfile(target):
                return target, None
            raise ToolError(f"文件不存在: {filename}")

        # 2) 精确路径匹配：相对 Skill 目录 / 相对项目根目录
        exact_candidates = [
            os.path.realpath(os.path.join(skill.directory, filename)),
            os.path.realpath(os.path.join(self._project_root, filename)),
        ]
        exact = [c for c in exact_candidates if os.path.isfile(c)]
        unique = list(dict.fromkeys(exact))
        if len(unique) == 1:
            target = unique[0]
            if not _is_within(skill_dir_real, target):
                raise ToolError(f"文件超出 Skill 目录范围，禁止读取: {filename}")
            return target, None
        if len(unique) > 1:
            # 多个路径均命中且指向不同文件：交由模型决定
            return None, self._candidate_message(skill, unique)

        # 3) 兜底：按文件名递归搜索 Skill 目录
        basename = os.path.basename(filename)
        found: List[str] = []
        for root, _dirs, files in os.walk(skill.directory):
            for f in files:
                if f == basename:
                    found.append(os.path.realpath(os.path.join(root, f)))
        found = list(dict.fromkeys(found))
        if not found:
            raise ToolError(f"在 Skill `{skill.name}` 目录内未找到文件: {filename}")
        if len(found) == 1:
            return found[0], None
        return None, self._candidate_message(skill, found)

    @staticmethod
    def _candidate_message(skill: SkillInfo, candidates: List[str]) -> str:
        lines = [
            f"在 Skill `{skill.name}` 内发现多个同名文件，请指定完整路径后再读取："
        ]
        for path in candidates:
            lines.append(f"- {path}")
        return "\n".join(lines)

    def load(self, name: str, filename: Optional[str] = None) -> str:
        """读取 Skill 的 SKILL.md 全文（无 filename），或指定的附件文件。"""
        skill = self._skills.get(name)
        if skill is None:
            known = ", ".join(sorted(self._skills)) or "(无)"
            return f"未找到技能 `{name}`。当前可用技能: {known}"
        if filename is None or not filename.strip():
            path = os.path.join(skill.directory, "SKILL.md")
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    return f"{skill.name} 的 SKILL.md 全文如下:\n" + _clip_content(fh.read())
            except OSError as exc:
                return f"读取 SKILL.md 失败: {exc}"
        try:
            target, candidates = self._resolve_file(skill, filename)
        except ToolError as exc:
            return f"工具执行失败: {exc}"
        if candidates is not None:
            # 多个同名文件：返回候选路径，再由模型决定
            return candidates
        if target is None:
            return f"无法解析文件: {filename}"
        try:
            with open(target, "r", encoding="utf-8") as fh:
                return f"{os.path.basename(target)} 内容如下:\n" + _clip_content(fh.read())
        except OSError as exc:
            return f"读取文件失败: {exc}"


def build_load_skill_tool(manager: SkillManager) -> ToolSpec:
    """构建 loadSkill 工具声明，绑定到给定 SkillManager。"""
    return ToolSpec(
        name="loadSkill",
        description=(
            "载入一个 Skill 的完整说明（SKILL.md 全文）或 Skill 目录内的附件文件。"
            "传入 name 时读取对应 Skill 的 SKILL.md；同时传 filename 时读取该附件，"
            "不再重复载入 SKILL.md。filename 支持相对 Skill 目录、相对项目根目录、"
            "绝对路径，或仅文件名（文件名会在 Skill 目录内递归搜索，多个同名时返回候选路径）。"
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "name": {
                    "type": "string",
                    "description": "要载入的 Skill 名称，取自系统提示中的可用技能列表",
                },
                "filename": {
                    "type": "string",
                    "description": "可选的附件文件名或路径；提供后只读附件，不载入 SKILL.md",
                },
            },
            "required": ["name"],
        },
        handler=manager.load,
    )
