from __future__ import annotations

"""
commands/add_signal_definition_to_gil.py

兼容入口（薄 wrapper）：
- 统一入口 `python -m ugc_file_tools tool add_signal_definition_to_gil ...` 仍指向本模块；
- 实际实现与 CLI 参数解析集中维护在 `ugc_file_tools.signal_writeback`，避免两份逻辑漂移。
"""

from ugc_file_tools.signal_writeback.cli import main
from ugc_file_tools.signal_writeback.writer import add_signals_to_gil

__all__ = [
    "add_signals_to_gil",
    "main",
]


if __name__ == "__main__":
    main()


