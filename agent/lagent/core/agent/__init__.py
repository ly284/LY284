"""Agent 业务核心（与界面无关）。"""

from __future__ import annotations

from typing import Optional

from ..config import AgentConfig, AppConfig, ConfigError, LLMConfig, load_config
from ..session import Conversation
from .engine import AgentEngine

__all__ = [
    "AgentConfig",
    "AgentEngine",
    "AppConfig",
    "ConfigError",
    "Conversation",
    "LLMConfig",
    "load_config",
    "create_agent",
]


def create_agent(config: Optional[AppConfig] = None, config_path: Optional[str] = None) -> AgentEngine:
    """按配置组装一个完整的 Agent 引擎。

    这是 UI 层唯一的组装入口：新增界面（Web/Desktop）时复用它，
    不需要重复拼装 LLM 客户端与工具注册表。
    """
    # 延迟导入，保持 core 包顶层轻量、避免循环依赖
    from ..llm.client import LLMClient
    from ..tools import build_registry

    app_config = config or load_config(config_path)
    client = LLMClient(app_config.llm)
    registry = build_registry()
    conversation = Conversation(system_prompt=app_config.agent.system_prompt)
    return AgentEngine(
        client=client,
        registry=registry,
        conversation=conversation,
        max_rounds=app_config.agent.max_rounds,
    )
