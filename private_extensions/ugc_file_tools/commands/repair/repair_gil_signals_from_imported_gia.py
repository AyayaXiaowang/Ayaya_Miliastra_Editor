from __future__ import annotations

"""
兼容入口（ugc_file_tools tool repair_gil_signals_from_imported_gia）：
- CLI wrapper 保持模块名稳定，供 unified_cli/tool.py 动态 import
- 核心实现下沉到 `ugc_file_tools.gil_signal_repair.from_imported_gia`
"""

from ugc_file_tools.gil_signal_repair.from_imported_gia import (
    SignalEntryInfo,
    main,
    plan_dedupe_by_signal_index,
    repair_gil_signals_from_imported_gia,
)

__all__ = [
    "SignalEntryInfo",
    "plan_dedupe_by_signal_index",
    "repair_gil_signals_from_imported_gia",
    "main",
]


if __name__ == "__main__":
    main()

