from __future__ import annotations

import argparse
from pathlib import Path


def register_workspace_diag_commands(subparsers: argparse._SubParsersAction) -> None:
    subparsers.add_parser(
        "print-workspace",
        help="打印当前解析到的 workspace_root 与 assets 路径（用于排查路径问题）",
    ).set_defaults(_runner=run_print_workspace)


def run_print_workspace(_parsed_args: argparse.Namespace, workspace_root: Path) -> int:
    print(f"workspace_root: {workspace_root}")
    print(f"assets_dir:     {workspace_root / 'assets'}")
    return 0

