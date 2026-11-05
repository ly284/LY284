"""Agent 业务核心（与界面无关）。"""

from __future__ import annotations

import os
from typing import Optional

from ..config import AgentConfig, AppConfig, ConfigError, LLMConfig, load_config
from ..session import Conversation
from .engine import AgentEngine, TurnCancelled

__all__ = [
    "AgentConfig",
    "AgentEngine",
    "AppConfig",
    "ConfigError",
    "Conversation",
    "LLMConfig",
    "load_config",
    "create_agent",
    "TurnCancelled",
]


def create_agent(config: Optional[AppConfig] = None, config_path: Optional[str] = None) -> AgentEngine:
    """按配置组装一个完整的 Agent 引擎。

    这是 UI 层唯一的组装入口：新增界面（Web/Desktop）时复用它，
    不需要重复拼装 LLM 客户端与工具注册表。
    """
    # 延迟导入，保持 core 包顶层轻量、避免循环依赖
    from ..llm.client import DEFAULT_TIMEOUT, LLMClient
    from ..skills import SkillManager, build_load_skill_tool
    from ..tools import build_registry

    app_config = config or load_config(config_path)

    client = LLMClient(app_config.llm, timeout=DEFAULT_TIMEOUT)
    registry = build_registry(
        search_api_key=app_config.search.api_key,
        search_endpoint=app_config.search.endpoint,
        search_timeout=app_config.search.timeout,
    )

    # Agent Skills 动态加载：以程序启动时的工作目录为项目根目录发现技能，
    # 注册 loadSkill 工具，并把技能清单注入 System Prompt。
    skill_manager = SkillManager(
        project_root=os.getcwd(), skills_dir=app_config.agent.skills_dir
    )
    if skill_manager.enabled:
        registry.register(build_load_skill_tool(skill_manager))

    skills_prompt = skill_manager.inject_prompt()
    system_prompt = app_config.agent.system_prompt
    if skills_prompt:
        system_prompt = "\n\n".join(
            part for part in (system_prompt, skills_prompt) if part
        )

    conversation = Conversation(system_prompt=system_prompt)
    return AgentEngine(
        client=client,
        registry=registry,
        conversation=conversation,
        max_rounds=app_config.agent.max_rounds,
    )
