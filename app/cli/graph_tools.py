from __future__ import annotations

"""
Ayaya_Miliastra_Editor 便携版工具入口（CLI）。

目标：
- 源码环境：支持 `python -X utf8 -m app.cli.graph_tools ...`
- PyInstaller 冻结环境：支持 `Ayaya_Miliastra_Editor_Tools.exe ...`（无需用户安装 Python）

约定：
- 冻结运行时默认以 exe 所在目录作为 workspace_root，并在启动阶段 chdir 到该目录；
  因此发布产物要求 `assets/` 与 exe 同级外置（用户可编辑）。
- 本工具只做静态校验/检查，不执行任何节点业务逻辑（与引擎校验边界一致）。
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence


if not __package__ and not getattr(sys, "frozen", False):
    raise SystemExit(
        "请从项目根目录使用模块方式运行：\n"
        "  python -X utf8 -m app.cli.graph_tools --help\n"
        "（不再支持通过脚本内 sys.path.insert 的方式运行）"
    )

# workspace_root 推导与 settings 初始化唯一真源
from engine.utils.workspace import resolve_workspace_root, init_settings_for_workspace

# 仅在“模块运行 / 冻结运行”模式下导入引擎依赖，避免用户误用 `python app/cli/graph_tools.py`
# 时因 sys.path 未注入而出现误导性 ImportError。
from engine.utils.logging.console_encoding import (  # noqa: E402
    install_utf8_streams_on_windows as _install_utf8_streams_on_windows_impl,
)

from app.cli.commands import register_all_graph_tools_commands  # noqa: E402


def _install_utf8_streams_on_windows() -> None:
    _install_utf8_streams_on_windows_impl(errors="replace")


def _parse_cli(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="graph_tools",
        description="Ayaya_Miliastra_Editor 工具入口（校验/诊断）",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--root",
        dest="workspace_root",
        default="",
        help="工作区根目录（默认：源码=仓库根目录；冻结=exe 所在目录）",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    register_all_graph_tools_commands(subparsers)
    return parser.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    _install_utf8_streams_on_windows()

    argv_list: Sequence[str] = sys.argv[1:] if argv is None else argv
    parsed_args = _parse_cli(argv_list)

    workspace_root_text = str(parsed_args.workspace_root).strip() if hasattr(parsed_args, "workspace_root") else ""
    workspace_root = resolve_workspace_root(
        workspace_root_text if workspace_root_text else None,
        start_paths=[Path(__file__).resolve()],
    )

    os.chdir(workspace_root)

    from engine.configs.settings import settings

    # 工具入口默认开启信息级日志，确保用户可见关键进度（与 CLI 约定一致）。
    # 例外：validate-graphs / ui-var 的 --json 模式要求 stdout 仅输出 JSON（便于脚本/CI 消费），
    # 因此需关闭 info 日志避免混入前置文本。
    enable_info_logs = True
    if parsed_args.command in {"validate-graphs", "ui-var"} and bool(getattr(parsed_args, "output_json", False)):
        enable_info_logs = False
    settings.NODE_IMPL_LOG_VERBOSE = bool(enable_info_logs)
    init_settings_for_workspace(workspace_root=workspace_root, load_user_settings=False)

    runner = getattr(parsed_args, "_runner", None)
    if runner is None:
        raise SystemExit(f"未知命令: {parsed_args.command}")

    return int(runner(parsed_args, workspace_root))


if __name__ == "__main__":
    sys.exit(main())

