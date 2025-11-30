from __future__ import annotations

import builtins as _builtins
import sys
from typing import Any

__all__ = ["install_ascii_safe_print", "ascii_safe_print"]

_ASCII_REPLACEMENTS: dict[str, str] = {
    "✓": "[OK]",
    "✅": "[OK]",
    "✗": "[FAIL]",
    "❌": "[FAIL]",
    "⚠️": "[WARN]",
    "⚠": "[WARN]",
    "⟳": "[BUSY]",
    "→": "->",
    "←": "<-",
    "↔": "<->",
    "↻": "[REFRESH]",
    "↺": "[RETRY]",
    "…": "...",
    "—": "-",
    "–": "-",
    "·": "-",
    "•": "-",
    "●": "*",
    ">": ">",
    "▶️": ">",
    "▶": ">",
    "⚙️": "[SETTINGS]",
    "⚙": "[SETTINGS]",
    "☆": "*",
    "★": "*",
}

_ORIGINAL_PRINT = _builtins.print


def _sanitize_console_text(text: object) -> str:
    value = text if isinstance(text, str) else str(text)
    result = value
    for special_char, ascii_text in _ASCII_REPLACEMENTS.items():
        if special_char in result:
            result = result.replace(special_char, ascii_text)
    return result


def ascii_safe_print(*objects: object, **kwargs: Any) -> None:
    """以 ASCII 安全方式打印内容，不依赖全局 patch。"""
    separator = kwargs.get("sep", " ")
    line_ending = kwargs.get("end", "\n")
    output_file = kwargs.get("file", sys.stdout)
    flush_flag = bool(kwargs.get("flush", False))

    sanitized_args = [_sanitize_console_text(obj) for obj in objects]
    sanitized_sep = _sanitize_console_text(separator)
    sanitized_end = _sanitize_console_text(line_ending)

    _ORIGINAL_PRINT(
        *sanitized_args,
        sep=sanitized_sep,
        end=sanitized_end,
        file=output_file,
        flush=flush_flag,
    )


def install_ascii_safe_print() -> None:
    """安装 ASCII 安全的全局 print，避免 Windows 控制台编码问题。

    仅替换已知问题符号为 ASCII 等价形式，不改变中文内容；
    UI 日志与业务逻辑不受影响。
    """

    _builtins.print = ascii_safe_print  # type: ignore[assignment]


