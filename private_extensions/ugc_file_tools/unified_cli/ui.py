from __future__ import annotations

import argparse

from .ui_dump import register_ui_dump_subcommands
from .ui_item_displays import register_ui_item_displays_subcommands
from .ui_custom_variables import register_ui_custom_variables_subcommands
from .ui_layouts import register_ui_layouts_subcommands
from .ui_progressbars import register_ui_progressbars_subcommands
from .ui_roundtrip import register_ui_roundtrip_subcommands
from .ui_textboxes import register_ui_textboxes_subcommands
from .ui_web_import import register_ui_web_import_subcommands


def add_subparser_ui(subparsers: argparse._SubParsersAction) -> None:
    ui_parser = subparsers.add_parser("ui", help="修改 .gil（UI TextBox）相关功能")
    ui_subparsers = ui_parser.add_subparsers(dest="ui_command", required=True)

    register_ui_dump_subcommands(ui_subparsers)
    register_ui_roundtrip_subcommands(ui_subparsers)
    register_ui_progressbars_subcommands(ui_subparsers)
    register_ui_layouts_subcommands(ui_subparsers)
    register_ui_textboxes_subcommands(ui_subparsers)
    register_ui_web_import_subcommands(ui_subparsers)
    register_ui_item_displays_subcommands(ui_subparsers)
    register_ui_custom_variables_subcommands(ui_subparsers)


