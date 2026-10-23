"""lagent 业务核心包。

分层结构：
- config / events：配置与事件契约（UI 与 core 的边界）
- llm：模型通信层（OpenAI 兼容客户端、思考内容过滤）
- tools：能力层（模型可调用的本地工具）
- session：会话状态层（消息历史与回滚）
- agent：编排层（主循环，产出事件流）
"""

from __future__ import annotations

from .config import AgentConfig, AppConfig, ConfigError, LLMConfig, load_config
from .agent import AgentEngine, create_agent

__all__ = [
    "AgentConfig",
    "AgentEngine",
    "AppConfig",
    "ConfigError",
    "LLMConfig",
    "create_agent",
    "load_config",
]
