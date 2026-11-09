"""允许 `python -m tui` 直接启动 TUI。"""

from __future__ import annotations

import sys

from main import main as _main


def main() -> int:
    return _main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())