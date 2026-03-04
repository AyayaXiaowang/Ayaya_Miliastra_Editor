from __future__ import annotations

"""`.gil` → Graph_Generater 项目存档导出器（模块化实现）。"""

from typing import Any


def export_gil_to_package(*args: Any, **kwargs: Any) -> Any:
    """
    延迟导入：避免在 import 阶段触发重依赖初始化，确保 `--help` / 轻量工具可用。

    真实实现位于 `runner.py`。
    """
    from .runner import export_gil_to_package as _export_gil_to_package

    return _export_gil_to_package(*args, **kwargs)


