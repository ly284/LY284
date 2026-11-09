"""lagent 入口：解析命令行、组装 core、启动界面。

界面通过 UI_RUNNERS 注册表扩展，未来新增 Web / Desktop 界面时
只需增加一 条注册项，无需改动 core。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Callable, Dict, Optional

from core import ConfigError, create_agent, load_config
from core.config import AppConfig, DEFAULT_CONFIG_FILE, write_default_config

__all__ = ["UI_RUNNERS", "build_parser", "main"]


def _run_tui(config: AppConfig, config_hint: Optional[str] = None) -> int:
    from tui.app import AgentApp

    engine = create_agent(config)
    AgentApp(engine, config_hint=config_hint).run()
    return 0


# 界面注册表：名称 -> 启动函数。未来 Web/Desktop 在此扩展。
UI_RUNNERS: Dict[str, Callable[[AppConfig, Optional[str]], int]] = {
    "tui": _run_tui,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lagent",
        description="带工具调用能力的终端 Agent（core 与界面分离，可扩展多界面）",
    )
    parser.add_argument(
        "-c", "--config", default=None, help="config.ini 路径（默认当前目录）"
    )
    parser.add_argument(
        "-u",
        "--ui",
        default="tui",
        choices=sorted(UI_RUNNERS),
        help="要启动的界面，默认 tui",
    )
    parser.add_argument(
        "--base-url", default=None, help="覆盖配置中的 base_url"
    )
    parser.add_argument("--model", default=None, help="覆盖配置中的 model")
    parser.add_argument("--api-key", default=None, help="覆盖配置中的 api_key")
    return parser


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)

    # 未显式指定 config 且当前目录没有配置时，自动创建一份含 mock 值的模板，
    # 启动后弹出对话框提示用户修改 config.ini 并重新启动。
    config_hint: Optional[str] = None
    if args.config is None and not os.environ.get("LAGENT_CONFIG", "").strip():
        config_path = Path(DEFAULT_CONFIG_FILE)
        if not config_path.is_file():
            try:
                config_hint = write_default_config(config_path)
            except OSError as exc:
                print(f"无法创建示例配置 config.ini: {exc}", file=sys.stderr)
                return 2

    try:
        config = load_config(
            args.config,
            base_url=args.base_url,
            model=args.model,
            api_key=args.api_key,
        )
    except ConfigError as exc:
        print(f"配置错误: {exc}", file=sys.stderr)
        return 2

    runner = UI_RUNNERS[args.ui]
    return runner(config, config_hint)


if __name__ == "__main__":
    raise SystemExit(main())
