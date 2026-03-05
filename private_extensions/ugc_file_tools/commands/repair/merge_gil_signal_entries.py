from __future__ import annotations

"""
兼容入口（ugc_file_tools tool merge_gil_signal_entries）：
- CLI wrapper 保持模块名稳定，供 unified_cli/tool.py 动态 import
- 核心实现下沉到 `ugc_file_tools.gil_signal_repair.merge_signal_entries`
"""

from ugc_file_tools.gil_signal_repair.merge_signal_entries import main, merge_gil_signal_entries

__all__ = [
    "merge_gil_signal_entries",
    "main",
]


if __name__ == "__main__":
    main()

