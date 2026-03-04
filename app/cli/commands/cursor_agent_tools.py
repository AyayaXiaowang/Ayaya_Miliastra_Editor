from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def register_cursor_agent_commands(subparsers: argparse._SubParsersAction) -> None:
    models_parser = subparsers.add_parser(
        "cursor-models",
        help="列出当前账号可用的 Cursor Agent 模型（调用本机 agent CLI）",
    )
    models_parser.set_defaults(_runner=run_cursor_models)

    agent_parser = subparsers.add_parser(
        "cursor-agent",
        help=(
            "通过 Cursor Agent CLI 运行一个提示（调用本机 agent CLI）。\n"
            "用法建议：将 agent 的参数放在 `--` 之后透传，例如：\n"
            "  python -X utf8 -m app.cli.graph_tools cursor-agent -- --print --output-format json \"你好\""
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    agent_parser.add_argument(
        "agent_args",
        nargs=argparse.REMAINDER,
        help="透传给 agent 的参数与 prompt（建议使用 `--` 分隔）。",
    )
    agent_parser.set_defaults(_runner=run_cursor_agent)


def _resolve_agent_executable() -> str:
    agent_exe = shutil.which("agent")
    if not agent_exe:
        raise SystemExit(
            "[ERROR] 未找到 Cursor Agent CLI（agent）。\n"
            "请确认已安装 Cursor Agent 命令行工具，并确保 agent 在 PATH 中可用。\n"
            "可用性检查示例：\n"
            "  agent --version\n"
            "  agent --help"
        )
    return agent_exe


def _run_external(argv: list[str], workspace_root: Path) -> int:
    completed = subprocess.run(
        argv,
        cwd=str(workspace_root),
        check=False,
    )
    return int(completed.returncode)


def run_cursor_models(_parsed_args: argparse.Namespace, workspace_root: Path) -> int:
    agent_exe = _resolve_agent_executable()
    return _run_external([agent_exe, "--list-models"], workspace_root=workspace_root)


def run_cursor_agent(parsed_args: argparse.Namespace, workspace_root: Path) -> int:
    agent_exe = _resolve_agent_executable()
    forwarded = list(getattr(parsed_args, "agent_args", []) or [])
    if not forwarded:
        raise SystemExit(
            "[ERROR] 缺少透传参数/提示词。\n"
            "示例：\n"
            "  python -X utf8 -m app.cli.graph_tools cursor-agent -- --print \"你好\""
        )
    return _run_external([agent_exe, *forwarded], workspace_root=workspace_root)

