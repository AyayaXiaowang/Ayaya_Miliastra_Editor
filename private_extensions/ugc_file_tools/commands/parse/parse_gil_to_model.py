from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, Optional

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.gil.pipeline import (
    add_gil_to_package_export_arguments,
    add_parsed_summary_output_argument,
    load_parsed_summary_dict,
    resolve_gil_to_package_export_config,
    run_export_gil_to_package,
    write_parsed_summary_json,
)
from ugc_file_tools.commands.generate_graph_code_from_package import generate_graph_code_for_package_root


def main(argv: Optional[Iterable[str]] = None) -> None:
    configure_console_encoding()

    argument_parser = argparse.ArgumentParser(
        description="一键解析 .gil：先导出为 Graph_Generater 项目存档目录，再加载为“程序可识别”的结构化摘要 JSON。",
    )
    add_gil_to_package_export_arguments(argument_parser)
    add_parsed_summary_output_argument(argument_parser)
    argument_parser.add_argument(
        "--generate-graph-code",
        dest="generate_graph_code",
        action="store_true",
        help="可选：从导出的项目存档自动生成 Graph Code（节点图/client 与 节点图/server）。",
    )
    argument_parser.add_argument(
        "--graph-code-overwrite",
        dest="graph_code_overwrite",
        action="store_true",
        help="生成 Graph Code 时是否覆盖已存在的节点图 .py 文件（默认不覆盖）。",
    )

    arguments = argument_parser.parse_args(list(argv) if argv is not None else None)

    export_config = resolve_gil_to_package_export_config(arguments)
    run_export_gil_to_package(export_config)

    parsed_summary = load_parsed_summary_dict(package_root=export_config.output_package_root)
    parsed_output_path = write_parsed_summary_json(
        output_package_root=export_config.output_package_root,
        parsed_summary=parsed_summary,
        parsed_output_json=str(arguments.parsed_output_json or ""),
    )
    print(f"已写入解析摘要: {parsed_output_path.resolve()}")

    if bool(arguments.generate_graph_code):
        generate_result = generate_graph_code_for_package_root(
            export_config.output_package_root,
            overwrite=bool(arguments.graph_code_overwrite),
        )
        generated_files = list(generate_result.get("generated_files", []))
        skipped_files = list(generate_result.get("skipped_files", []))
        print("=" * 80)
        print("已完成 Graph Code 自动生成：")
        print(f"- client_dir: {generate_result.get('output_client_dir')}")
        print(f"- server_dir: {generate_result.get('output_server_dir')}")
        print(f"- generated: {len(generated_files)}")
        print(f"- skipped: {len(skipped_files)}")
        print("=" * 80)


if __name__ == "__main__":
    main()




