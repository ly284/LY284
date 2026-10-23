"""配置加载：从 config.ini 读取 LLM 连接信息，支持环境变量覆盖。"""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

__all__ = ["LLMConfig", "AgentConfig", "AppConfig", "ConfigError", "load_config"]

DEFAULT_CONFIG_FILE = "config.ini"
ENV_API_KEY = "LAGENT_API_KEY"
ENV_BASE_URL = "LAGENT_BASE_URL"
ENV_MODEL = "LAGENT_MODEL"
ENV_CONFIG = "LAGENT_CONFIG"


class ConfigError(Exception):
    """配置缺失或不合法。"""


@dataclass(frozen=True)
class LLMConfig:
    """大模型服务连接参数。"""

    base_url: str
    model: str
    api_key: str

    @property
    def masked_api_key(self) -> str:
        key = self.api_key or ""
        if len(key) <= 8:
            return "***" if key else "(空)"
        return f"{key[:4]}***{key[-4:]}"


@dataclass(frozen=True)
class AgentConfig:
    """Agent 行为参数。"""

    max_rounds: int = 5
    system_prompt: str = ""


@dataclass(frozen=True)
class AppConfig:
    """应用总配置。"""

    llm: LLMConfig
    agent: AgentConfig


def _read_ini(path: Path) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    try:
        with path.open("r", encoding="utf-8") as fh:
            cfg.read_file(fh)
    except OSError as exc:
        raise ConfigError(f"无法读取配置文件: {path} ({exc})") from exc
    except configparser.Error as exc:
        raise ConfigError(f"配置文件格式错误: {path} ({exc})") from exc
    return cfg


def _pick(cli_value: Optional[str], env_name: str, ini_value: str) -> str:
    """按 命令行 > 环境变量 > 配置文件 的顺序取值。"""
    if cli_value:
        return cli_value.strip()
    env_value = os.environ.get(env_name, "")
    if env_value.strip():
        return env_value.strip()
    return (ini_value or "").strip()


def load_config(
    path: Optional[str] = None,
    *,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> AppConfig:
    """加载配置。

    文件查找顺序：显式 path > 环境变量 LAGENT_CONFIG > 当前工作目录 config.ini。
    """
    config_path = Path(path) if path else None
    if config_path is None:
        env_path = os.environ.get(ENV_CONFIG, "").strip()
        config_path = Path(env_path) if env_path else Path(DEFAULT_CONFIG_FILE)

    if config_path.is_file():
        cfg = _read_ini(config_path)
    elif path is not None or os.environ.get(ENV_CONFIG, "").strip():
        raise ConfigError(f"未找到配置文件: {config_path.absolute()}")
    else:
        cfg = configparser.ConfigParser()

    if not cfg.has_section("llm"):
        raise ConfigError(
            f"配置文件缺少 [llm] 段: {config_path.absolute()}；"
            f"也可以通过环境变量 {ENV_API_KEY} / {ENV_BASE_URL} / {ENV_MODEL} 提供"
        )

    sec = cfg["llm"]
    resolved_base_url = _pick(base_url, ENV_BASE_URL, sec.get("base_url", ""))
    resolved_model = _pick(model, ENV_MODEL, sec.get("model", ""))
    resolved_api_key = _pick(api_key, ENV_API_KEY, sec.get("api_key", ""))

    if not resolved_base_url:
        raise ConfigError(f"缺少 base_url：请在 [llm] 段或环境变量 {ENV_BASE_URL} 中配置")
    if not resolved_model:
        raise ConfigError(f"缺少 model：请在 [llm] 段或环境变量 {ENV_MODEL} 中配置")
    if not resolved_api_key:
        raise ConfigError(f"缺少 api_key：请在 [llm] 段或环境变量 {ENV_API_KEY} 中配置")

    agent_sec = cfg["agent"] if cfg.has_section("agent") else {}
    try:
        max_rounds = int(agent_sec.get("max_rounds", "5") or "5")
    except ValueError as exc:
        raise ConfigError("agent.max_rounds 必须是整数") from exc
    if max_rounds < 1:
        raise ConfigError("agent.max_rounds 必须 >= 1")

    return AppConfig(
        llm=LLMConfig(
            base_url=resolved_base_url,
            model=resolved_model,
            api_key=resolved_api_key,
        ),
        agent=AgentConfig(
            max_rounds=max_rounds,
            system_prompt=(agent_sec.get("system_prompt", "") or "").strip(),
        ),
    )
