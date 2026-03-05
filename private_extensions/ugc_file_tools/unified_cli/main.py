from __future__ import annotations

import argparse
from typing import Iterable

from ugc_file_tools.console_encoding import configure_console_encoding

from .entity import add_subparser_entity
from .gui import add_subparser_gui
from .project import add_subparser_project
from .tool import add_subparser_tool
from .ui import add_subparser_ui


def main(argv: Iterable[str] | None = None) -> None:
    configure_console_encoding()

    argument_parser = argparse.ArgumentParser(
        description="UGC 一体化工具：同时支持 UI TextBox（.gil）与实体（.gia）操作。",
    )
    subparsers = argument_parser.add_subparsers(dest="command", required=True)

    add_subparser_ui(subparsers)
    add_subparser_entity(subparsers)
    add_subparser_project(subparsers)
    add_subparser_tool(subparsers)
    add_subparser_gui(subparsers)

    arguments = argument_parser.parse_args(list(argv) if argv is not None else None)
    entrypoint = getattr(arguments, "entrypoint", None)
    if entrypoint is None:
        raise RuntimeError("命令解析失败：未找到入口函数")
    entrypoint(arguments)




