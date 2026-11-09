"""配置加载：从 config.ini 读取 LLM 连接信息，支持环境变量覆盖。"""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

__all__ = [
    "LLMConfig",
    "AgentConfig",
    "SearchConfig",
    "AppConfig",
    "ConfigError",
    "DEFAULT_CONFIG_TEMPLATE",
    "load_config",
    "write_default_config",
]

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
    context_window: Optional[int] = None

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
    skills_dir: str = ""
    context_dir: str = ".agents/context"
    sessions_dir: str = ".agents/sessions"
    compress_threshold: float = 0.6


@dataclass(frozen=True)
class SearchConfig:
    """网络搜索服务配置（百度千帆 AI 搜索）。"""

    api_key: str = ""
    endpoint: str = "https://qianfan.baidubce.com/v2/ai_search/web_search"
    timeout: float = 30.0

    @property
    def enabled(self) -> bool:
        return bool((self.api_key or "").strip())


@dataclass(frozen=True)
class AppConfig:
    """应用总配置。"""

    llm: LLMConfig
    agent: AgentConfig
    search: SearchConfig = field(default_factory=SearchConfig)


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

    context_window: Optional[int] = None
    raw_window = (sec.get("context_window", "") or "").strip()
    if raw_window:
        try:
            context_window = int(raw_window)
        except ValueError as exc:
            raise ConfigError("llm.context_window 必须是整数") from exc
        if context_window < 1:
            raise ConfigError("llm.context_window 必须 >= 1")

    if not resolved_base_url:
        raise ConfigError(f"缺少 base_url：请在 [llm] 段或环境变量 {ENV_BASE_URL} 中配置")
    if not resolved_model:
        raise ConfigError(f"缺少 model：请在 [llm] 段或环境变量 {ENV_MODEL} 中配置")
    if not resolved_api_key:
        raise ConfigError(f"缺少 api_key：请在 [llm] 段或环境变量 {ENV_API_KEY} 中配置")

    search_sec = cfg["search"] if cfg.has_section("search") else {}
    try:
        search_timeout = float((search_sec.get("timeout", "30") or "30").strip())
    except ValueError as exc:
        raise ConfigError("search.timeout 必须是数值") from exc
    search_config = SearchConfig(
        api_key=(search_sec.get("api_key", "") or "").strip(),
        endpoint=(search_sec.get("endpoint", "") or "").strip()
        or "https://qianfan.baidubce.com/v2/ai_search/web_search",
        timeout=search_timeout,
    )

    agent_sec = cfg["agent"] if cfg.has_section("agent") else {}
    try:
        max_rounds = int(agent_sec.get("max_rounds", "5") or "5")
    except ValueError as exc:
        raise ConfigError("agent.max_rounds 必须是整数") from exc
    if max_rounds < 1:
        raise ConfigError("agent.max_rounds 必须 >= 1")

    try:
        compress_threshold = float(agent_sec.get("compress_threshold", "0.6") or "0.6")
    except ValueError as exc:
        raise ConfigError("agent.compress_threshold 必须是数值（0~1）") from exc
    compress_threshold = min(1.0, max(0.01, compress_threshold))

    context_dir = (agent_sec.get("context_dir", "") or "").strip() or ".agents/context"
    sessions_dir = (agent_sec.get("sessions_dir", "") or "").strip() or ".agents/sessions"

    return AppConfig(
        llm=LLMConfig(
            base_url=resolved_base_url,
            model=resolved_model,
            api_key=resolved_api_key,
            context_window=context_window,
        ),
        agent=AgentConfig(
            max_rounds=max_rounds,
            system_prompt=(agent_sec.get("system_prompt", "") or "").strip(),
            skills_dir=(agent_sec.get("skills_dir", "") or "").strip(),
            context_dir=context_dir,
            sessions_dir=sessions_dir,
            compress_threshold=compress_threshold,
        ),
        search=search_config,
    )


DEFAULT_CONFIG_TEMPLATE = """# lagent 配置文件示例。
# 启动时若当前目录没有 config.ini，程序会自动创建本文件——
# 请把下方 api_key 修改为你自己的密钥后重新启动。

[llm]
base_url = https://api.siliconflow.cn/v1
model = deepseek-ai/DeepSeek-V4.1-Flash
api_key = sk-mock-please-edit-me
# 可选：当前模型的上下文窗口大小（Token）。留空时尝试向模型服务查询，
# 查询不到则默认使用 128k，并在界面标注「默认」。
# context_window = 128000

[search]
# 百度千帆 AI 搜索 API Key（可留空，searchWeb 工具会提示未启用）
api_key =

[agent]
# 每轮最多允许的模型-工具循环次数
max_rounds = 5
# 上下文占用达到该比例时提示执行 /compact（0~1）
compress_threshold = 0.6
# 上下文归档目录（压缩前保存完整原始上下文）
context_dir = .agents/context
# 会话保存目录（/new、/save、/resume 使用）
sessions_dir = .agents/sessions
# 可选：Agent 的系统提示词（追加到工具定义之前）
# system_prompt = 你是一名乐于助人的助手。
# 可选：技能目录（默认在项目根目录下查找 .agents/skills）
# skills_dir =
"""


def write_default_config(path: Optional[str] = None) -> str:
    """当前目录缺少 config.ini 时写入一份带 mock 值的完整配置模板。

    返回写入的绝对路径。内容可被 load_config 直接解析，保证程序仍能
    正常启动（界面弹出提示后退出）。
    """
    target = Path(path) if path else Path(DEFAULT_CONFIG_FILE)
    with open(target, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(DEFAULT_CONFIG_TEMPLATE)
    return str(target.absolute())
