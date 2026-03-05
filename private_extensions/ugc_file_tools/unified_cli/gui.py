from __future__ import annotations

import argparse


def add_subparser_gui(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "gui",
        help="启动 ugc_file_tools 的简易图形界面（Tkinter）。",
    )
    parser.set_defaults(entrypoint=_entry_gui)


def _entry_gui(_args: argparse.Namespace) -> None:
    from ugc_file_tools.apps.gui_app import main

    main()


