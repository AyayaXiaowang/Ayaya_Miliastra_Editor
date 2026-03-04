from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, Optional

from ugc_file_tools.gil.pipeline import (
    add_gil_to_package_export_arguments,
    add_parsed_summary_output_argument,
    load_parsed_summary_dict,
    resolve_gil_to_package_export_config,
    run_export_gil_to_package,
    write_parsed_summary_json,
)
from ugc_file_tools.integrations.graph_generater.graph_code_validation import validate_graph_code_for_package_root
from ugc_file_tools.package_parser.json_io import write_json_file

from ugc_file_tools.commands.generate_graph_code_from_package import generate_graph_code_for_package_root
from ugc_file_tools.console_encoding import configure_console_encoding


def main(argv: Optional[Iterable[str]] = None) -> None:
    configure_console_encoding()

    argument_parser = argparse.ArgumentParser(
        description=(
            "一键全量解析 .gil：导出为 Graph_Generater 项目存档目录 → 加载为“程序可识别”的结构化摘要 JSON → "
            "生成 Graph Code（含未识别图的占位图）→ 使用引擎验证 Graph Code。"
        ),
    )
    add_gil_to_package_export_arguments(argument_parser)
    add_parsed_summary_output_argument(argument_parser)
    argument_parser.add_argument(
        "--graph-code-overwrite",
        dest="graph_code_overwrite",
        action="store_true",
        help="生成 Graph Code 时是否覆盖已存在的节点图 .py 文件（默认不覆盖；占位图会被自动覆盖为更具体的实现）。",
    )
    argument_parser.add_argument(
        "--skip-graph-code",
        dest="skip_graph_code",
        action="store_true",
        help="跳过 Graph Code 生成步骤（默认不跳过）。",
    )
    argument_parser.add_argument(
        "--skip-validate-graph-code",
        dest="skip_validate_graph_code",
        action="store_true",
        help="跳过 Graph Code 校验步骤（默认不跳过）。",
    )
    argument_parser.add_argument(
        "--strict-graph-code",
        dest="strict_graph_code",
        action="store_true",
        help="Graph Code 校验：实体入参严格模式（仅允许连线/事件参数）。",
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

    if not bool(arguments.skip_graph_code):
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

    if not bool(arguments.skip_validate_graph_code):
        validation_report = validate_graph_code_for_package_root(
            export_config.output_package_root,
            strict_entity_wire_only=bool(arguments.strict_graph_code),
        )
        validation_output_path = export_config.output_package_root / "原始解析" / "graph_code_validation.json"
        write_json_file(validation_output_path, validation_report)
        print("=" * 80)
        print("Graph Code 校验完成：")
        print(f"- errors: {validation_report.get('errors')}")
        print(f"- warnings: {validation_report.get('warnings')}")
        print(f"- report: {validation_output_path.resolve()}")
        print("=" * 80)
        if int(validation_report.get("errors", 0) or 0) > 0:
            raise SystemExit(1)


if __name__ == "__main__":
    main()




