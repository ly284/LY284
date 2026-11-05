"""Agent Skills 动态加载机制。

初始化时发现项目根目录（程序启动时的工作目录）下各 Skill 子目录中的
SKILL.md，仅读取其 YAML Frontmatter 的 name / description；完整正文
只有模型调用 loadSkill 工具时才进入对话上下文。
"""

from __future__ import annotations

from .manager import SkillManager, build_load_skill_tool, discover_skills, resolve_skills_root

__all__ = [
    "SkillManager",
    "build_load_skill_tool",
    "discover_skills",
    "resolve_skills_root",
]
