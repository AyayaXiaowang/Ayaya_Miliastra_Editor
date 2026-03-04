from __future__ import annotations

"""
CLI thin entry: generate Graph Code for a project-archive package root.

实现下沉到库层：
- `ugc_file_tools.graph.code_generation_impl`（供 pipelines/库层复用）
- `ugc_file_tools.graph.code_generation`（稳定 facade）
"""

import argparse
from pathlib import Path
from typing import Iterable, Optional

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.graph.code_generation import generate_graph_code_for_package_root


def main(argv: Optional[Iterable[str]] = None) -> None:
    configure_console_encoding()

    argument_parser = argparse.ArgumentParser(
        description="从项目存档的 pyugc 节点图原始结构自动生成 Graph_Generater Graph Code（Python）。",
    )
    argument_parser.add_argument(
        "--package-root",
        dest="package_root",
        required=True,
        help="项目存档目录（例如 Graph_Generater/assets/资源库/项目存档/test2）",
    )
    argument_parser.add_argument(
        "--overwrite",
        dest="overwrite",
        action="store_true",
        help="若目标节点图文件已存在，是否覆盖（默认不覆盖）。",
    )

    arguments = argument_parser.parse_args(list(argv) if argv is not None else None)

    package_root_path = Path(arguments.package_root).resolve()
    result = generate_graph_code_for_package_root(
        package_root_path,
        overwrite=bool(arguments.overwrite),
    )

    print("=" * 80)
    print(f"生成完成：package={result.get('package_name')}")
    print(f"输出目录: {result.get('output_client_dir')}")
    print(f"输出目录: {result.get('output_server_dir')}")
    generated_files = list(result.get("generated_files", []))
    skipped_files = list(result.get("skipped_files", []))
    print(f"生成文件: {len(generated_files)}")
    for file_path in generated_files:
        print(f"  + {file_path.name}")
    print(f"跳过文件: {len(skipped_files)}")
    for file_path in skipped_files:
        print(f"  - {file_path.name}")
    print("=" * 80)


if __name__ == "__main__":
    main()

