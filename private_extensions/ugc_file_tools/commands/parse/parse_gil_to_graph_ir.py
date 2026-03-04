from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, Optional

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.commands.export_graph_ir_from_package import export_readable_graph_ir_for_package_root
from ugc_file_tools.gil.pipeline import add_gil_to_package_export_arguments, resolve_gil_to_package_export_config, run_export_gil_to_package


def main(argv: Optional[Iterable[str]] = None) -> None:
    """
    一键解析 `.gil` 的节点图（专注节点图部分）：
    - 可选：先导出为 Graph_Generater 项目存档目录（生成 pyugc_graphs/node_defs 等缓存）
    - 再从项目存档导出“可读节点图 IR”（包含 nodes + 完整 edges 解析）
    """
    configure_console_encoding()

    argument_parser = argparse.ArgumentParser(
        description="一键解析 .gil 的节点图：导出项目存档（可选）→ 导出可读节点图 IR（含 edges）。",
    )
    add_gil_to_package_export_arguments(argument_parser)
    argument_parser.add_argument(
        "--skip-export",
        dest="skip_export",
        action="store_true",
        help="若已存在项目存档导出结果，可跳过导出步骤，直接生成 IR。",
    )
    argument_parser.add_argument(
        "--no-markdown",
        dest="no_markdown",
        action="store_true",
        help="仅导出 JSON IR，不生成 Markdown 摘要。",
    )

    arguments = argument_parser.parse_args(list(argv) if argv is not None else None)

    export_config = resolve_gil_to_package_export_config(arguments)
    if not bool(arguments.skip_export):
        run_export_gil_to_package(export_config)

    ir_result = export_readable_graph_ir_for_package_root(
        export_config.output_package_root,
        write_markdown=(not bool(arguments.no_markdown)),
    )

    print("=" * 80)
    print("节点图 IR 导出完成：")
    print(f"- package_root: {ir_result.get('package_root')}")
    print(f"- output_dir: {ir_result.get('output_dir')}")
    print(f"- graphs_count: {ir_result.get('graphs_count')}")
    print(f"- index: {ir_result.get('index')}")
    print(f"- node_types_index: {ir_result.get('node_types_index')}")
    print("=" * 80)


if __name__ == "__main__":
    main()




