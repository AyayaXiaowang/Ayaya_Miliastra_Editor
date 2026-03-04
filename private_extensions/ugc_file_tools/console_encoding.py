from __future__ import annotations

"""
console_encoding.py

统一收口 CLI 的控制台编码配置，避免在大量脚本中重复出现样板代码。

约束：
- 不使用 try/except；若环境不支持 `reconfigure`，则保持默认行为。
"""

import sys

DEFAULT_CONSOLE_ENCODING = "utf-8"


def configure_console_encoding(encoding: str = DEFAULT_CONSOLE_ENCODING) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding=str(encoding))
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding=str(encoding))

# Backwards-compat shim: keep old private name for internal legacy callers.


def _configure_console_encoding() -> None:
    # 兼容历史脚本内部使用的私有函数名
    configure_console_encoding()



