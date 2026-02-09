"""
节点图代码严格验证器（运行时入口）

说明：
- 引擎侧统一入口位于 `engine.validate.node_graph_validator`；
- 本模块仅做运行时层的 re-export，便于节点图代码通过稳定路径使用：
  `from app.runtime.engine.node_graph_validator import validate_node_graph`
"""

from __future__ import annotations

import sys
from pathlib import Path

from engine.validate.node_graph_validator import (  # noqa: F401
    NodeGraphValidationError,
    NodeGraphValidator,
    format_validate_file_report,
    validate_node_graph,
    validate_file,
)


def validate_file_cli(file_path: str | Path) -> int:
    """校验单个节点图文件并打印结果（便于节点图文件内 `__main__` 一行调用）。

    用法（在节点图文件尾部）：
        if __name__ == "__main__":
            from app.runtime.engine.node_graph_validator import validate_file_cli
            raise SystemExit(validate_file_cli(__file__))
    """
    # 对齐工具侧（`app.cli.graph_tools validate-file`）的输出口径：
    # - Windows 下统一以 UTF-8 输出，避免中文乱码/编码异常
    # - “通过”也要打印警告明细，保证自检与工具校验结果一致
    from engine.utils.logging.console_encoding import install_utf8_streams_on_windows

    install_utf8_streams_on_windows(errors="replace")

    resolved_path = Path(file_path).resolve()

    # 对齐 UI：在校验前加载用户设置（如自动排版/relay 等开关），避免“UI 与自检”因 settings 不一致而口径漂移。
    # 注意：ensure_settings_workspace_root 会在 workspace_root 已注入时也尊重 load_user_settings=True（见 engine.utils.workspace）。
    from engine.utils.workspace import ensure_settings_workspace_root

    ensure_settings_workspace_root(
        start_paths=[resolved_path, Path(__file__).resolve()],
        load_user_settings=True,
    )
    passed, error_list, warning_list = validate_file(resolved_path)

    print(
        format_validate_file_report(
            file_path=resolved_path,
            passed=passed,
            errors=error_list,
            warnings=warning_list,
        )
    )

    if passed:
        return 0
    return 1


__all__ = [
    "NodeGraphValidationError",
    "NodeGraphValidator",
    "format_validate_file_report",
    "validate_node_graph",
    "validate_file",
    "validate_file_cli",
]
