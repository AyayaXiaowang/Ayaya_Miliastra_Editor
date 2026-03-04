from __future__ import annotations

import argparse


def register_all_graph_tools_commands(subparsers: argparse._SubParsersAction) -> None:
    from app.cli.commands.cursor_agent_tools import register_cursor_agent_commands
    from app.cli.commands.custom_var_tools import register_custom_var_tools_commands
    from app.cli.commands.graph_validation import register_graph_validation_commands
    from app.cli.commands.port_type_tools import register_port_type_tools_commands
    from app.cli.commands.project_tools import register_project_tools_commands
    from app.cli.commands.ui_tools import register_ui_tools_commands
    from app.cli.commands.validate_all import register_validate_all_command
    from app.cli.commands.workspace_diag import register_workspace_diag_commands

    register_graph_validation_commands(subparsers)
    register_port_type_tools_commands(subparsers)
    register_project_tools_commands(subparsers)
    register_ui_tools_commands(subparsers)
    register_custom_var_tools_commands(subparsers)
    register_validate_all_command(subparsers)
    register_workspace_diag_commands(subparsers)
    register_cursor_agent_commands(subparsers)

