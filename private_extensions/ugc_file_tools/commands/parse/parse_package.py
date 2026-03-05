from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, Optional

from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.package_parser import load_parsed_package
from ugc_file_tools.package_parser.json_io import write_json_file


def main(argv: Optional[Iterable[str]] = None) -> None:
    argument_parser = argparse.ArgumentParser(
        description="读取 Graph_Generater 的项目存档目录，并输出“程序可识别”的结构化 JSON（含节点图原始结构解析）。",
    )
    argument_parser.add_argument(
        "--package-root",
        dest="package_root",
        required=True,
        help="项目存档目录（例如 Graph_Generater/assets/资源库/项目存档/test2）",
    )
    argument_parser.add_argument(
        "--output",
        dest="output_json",
        default="",
        help="可选：输出 JSON 文件路径（默认不落盘，仅打印摘要）。",
    )

    arguments = argument_parser.parse_args(list(argv) if argv is not None else None)

    package_root_path = Path(arguments.package_root)
    parsed_package = load_parsed_package(package_root_path)

    summary = parsed_package.to_dict()
    resources_summary = summary.get("resources", {})
    node_graphs_summary = summary.get("node_graphs", {})

    print("=" * 80)
    print(f"项目存档: {parsed_package.package_name}")
    print(f"根目录: {parsed_package.package_root}")
    print("-" * 80)
    print("资源统计:")
    for key, value in resources_summary.items():
        print(f"  - {key}: {value}")
    print("-" * 80)
    print(
        "节点图统计:"
        f" node_defs={len(node_graphs_summary.get('node_defs', []))},"
        f" pyugc_graphs={len(node_graphs_summary.get('pyugc_graphs', []))}"
    )
    print("=" * 80)

    output_json_text = str(arguments.output_json or "").strip()
    if output_json_text != "":
        output_path = resolve_output_file_path_in_out_dir(Path(output_json_text))
        write_json_file(output_path, summary)
        print(f"已写入: {output_path.resolve()}")


if __name__ == "__main__":
    main()


