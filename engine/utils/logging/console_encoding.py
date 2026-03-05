from __future__ import annotations

import io
import sys

__all__ = ["install_utf8_streams_on_windows"]


def install_utf8_streams_on_windows(*, errors: str = "replace") -> None:
    """在 Windows 下将 stdout/stderr 包装为 UTF-8 输出。

    背景：部分用户环境（尤其是非 UTF-8 控制台）会导致中文输出乱码或抛出编码异常。
    该函数仅做流包装，不做任何业务逻辑；非 Windows 平台不做处理。
    """
    if sys.platform != "win32":
        return

    sys.stdout = io.TextIOWrapper(  # type: ignore[attr-defined]
        sys.stdout.buffer,
        encoding="utf-8",
        errors=errors,
    )
    sys.stderr = io.TextIOWrapper(  # type: ignore[attr-defined]
        sys.stderr.buffer,
        encoding="utf-8",
        errors=errors,
    )


