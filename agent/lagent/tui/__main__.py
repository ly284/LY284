"""允许 `python -m tui` 直接启动 TUI。"""

from __future__ import annotations

import sys

from core import create_agent, load_config
from tui.app import AgentApp


def main() -> int:
    try:
        engine = create_agent(load_config())
    except Exception as exc:  # noqa: BLE001 - 命令行入口统一提示
        print(f"启动失败: {exc}", file=sys.stderr)
        return 2
    AgentApp(engine).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
