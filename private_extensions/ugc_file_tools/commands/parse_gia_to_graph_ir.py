from __future__ import annotations

from ugc_file_tools.commands.parse.parse_gia_to_graph_ir import *  # noqa: F401,F403

if __name__ == "__main__":
    from ugc_file_tools.unified_cli.entry_guard import deny_direct_execution

    deny_direct_execution(tool_name="parse_gia_to_graph_ir")
