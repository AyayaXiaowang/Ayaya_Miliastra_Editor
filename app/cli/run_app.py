from __future__ import annotations

"""
UI 启动入口（CLI）。

职责边界：
- 本文件仅负责：CLI 参数解析、workspace_root 推导、settings 注入与少量启动开关。
- 具体 UI 启动装配（OCR 预热 → PyQt6 → QApplication → 主题/看门狗/异常钩子 → 主窗口）委托给
  `app.bootstrap.ui_bootstrap`，避免入口膨胀为巨函数。
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

if not __package__ and not getattr(sys, "frozen", False):
    raise SystemExit(
        "请从项目根目录使用模块方式运行：\n"
        "  python -X utf8 -m app.cli.run_app\n"
        "（不再支持通过脚本内 sys.path.insert 的方式运行）"
    )

from engine.utils.workspace import resolve_workspace_root, init_settings_for_workspace
from engine.configs.settings import settings
from engine.utils.logging.console_sanitizer import install_ascii_safe_print
from engine.utils.logging.logger import log_info, log_warn


def _parse_cli_args(argv: Sequence[str]) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        prog="run_app",
        description="Ayaya_Miliastra_Editor UI 启动入口",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--root",
        dest="workspace_root",
        default="",
        help="工作区根目录（默认：源码=仓库根目录；冻结=exe 所在目录）",
    )
    parser.add_argument(
        "--print-workspace",
        action="store_true",
        help="打印当前解析到的 workspace_root 与 assets 路径并退出（用于排查路径问题）",
    )
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="打印启动诊断信息并退出（不导入 OCR/PyQt；用于排查启动前路径与环境）",
    )
    parser.add_argument(
        "--log-file",
        dest="log_file",
        default="",
        help="将控制台输出同时写入指定文件（相对路径按 workspace_root 解析）",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="关闭 info 级启动日志（仅保留 warn/error；安全声明仍会输出）",
    )
    parser.add_argument(
        "--ocr-preload",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="是否在导入 PyQt6 前预热 OCR（默认：true；关闭可能触发 DLL 冲突）",
    )
    parser.add_argument(
        "--ui-freeze-watchdog",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="是否启用 UI 卡死看门狗（默认：true；超阈值自动 dump 全线程堆栈）",
    )
    parser.add_argument(
        "--safety-dialog",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="是否弹出安全声明对话框（默认：true；控制台仍会输出声明）",
    )
    parsed_args, remaining = parser.parse_known_args(list(argv))
    return parsed_args, list(remaining)

DEFAULT_WORKSPACE_ROOT = resolve_workspace_root(start_paths=[Path(__file__).resolve()])

SAFETY_NOTICE = (
    "【安全声明】小王千星工坊（Ayaya_Miliastra_Editor）仅用于离线教学、代码模拟与节点图研究。"
    "不得将任何脚本、自动化流程或鼠标指令连接至官方《原神》客户端或服务器，"
    "否则可能触发账号封禁、奖励回收等处罚。"
)


def main(argv: Sequence[str] | None = None) -> None:
    # 安装全局 ASCII 安全打印（避免 Windows 控制台编码问题）
    install_ascii_safe_print()

    argv_list: Sequence[str] = sys.argv[1:] if argv is None else argv
    parsed_args, qt_remaining_args = _parse_cli_args(argv_list)

    workspace_root_text = str(parsed_args.workspace_root).strip()
    workspace = resolve_workspace_root(workspace_root_text) if workspace_root_text else DEFAULT_WORKSPACE_ROOT

    if (not workspace.exists()) or (not workspace.is_dir()):
        raise SystemExit(f"[ERROR] 工作区目录不存在: {workspace}")

    assets_dir = workspace / "assets"
    if not assets_dir.is_dir():
        raise SystemExit(
            f"[ERROR] 未找到 assets 目录: {assets_dir}\n"
            "说明：便携版要求 assets/ 与 exe 同级外置；或使用 --root 指向包含 assets/ 的工作区根目录。"
        )

    log_file_text = str(getattr(parsed_args, "log_file", "") or "").strip()
    log_file_path: Path | None = None
    if log_file_text:
        raw_log_path = Path(log_file_text)
        resolved_log_path = raw_log_path if raw_log_path.is_absolute() else (workspace / raw_log_path)
        log_file_path = resolved_log_path.resolve()

    if bool(parsed_args.print_workspace):
        print(f"workspace_root: {workspace}")
        print(f"assets_dir:     {assets_dir}")
        return

    if bool(parsed_args.diagnose):
        user_settings_path = (workspace / "app" / "runtime" / "cache" / "user_settings.json").resolve()
        print("=" * 80)
        print("启动诊断（不导入 OCR / PyQt）：")
        print(f"workspace_root: {workspace}")
        print(f"assets_dir:     {assets_dir}")
        print(f"cwd:           {Path.cwd().resolve()}")
        print(f"python:        {sys.executable}")
        print(f"python_ver:    {sys.version.splitlines()[0]}")
        print(f"frozen:        {bool(getattr(sys, 'frozen', False))}")
        print(f"user_settings: {user_settings_path} (exists={user_settings_path.exists()})")
        print(f"log_file:      {log_file_path if log_file_path is not None else '(disabled)'}")
        print("=" * 80)
        return

    os.chdir(workspace)
    # 在应用创建前尽早加载用户设置，确保主题模式等开关在启动阶段生效
    init_settings_for_workspace(workspace_root=workspace, load_user_settings=True)
    # GUI/CLI 入口统一在启动阶段打开信息级日志，确保控制台可见关键进度
    settings.NODE_IMPL_LOG_VERBOSE = not bool(getattr(parsed_args, "quiet", False))

    from app.bootstrap.ui_bootstrap import UiRunConfig, run_ui_app  # noqa: E402

    ui_config = UiRunConfig(
        workspace_root=workspace,
        qt_args=list(qt_remaining_args),
        safety_notice_text=SAFETY_NOTICE,
        enable_ocr_preload=bool(getattr(parsed_args, "ocr_preload", True)),
        enable_ui_freeze_watchdog=bool(getattr(parsed_args, "ui_freeze_watchdog", True)),
        show_safety_notice_dialog=bool(getattr(parsed_args, "safety_dialog", True)),
        log_file_path=log_file_path,
    )
    sys.exit(run_ui_app(ui_config))


if __name__ == '__main__':
    main()


