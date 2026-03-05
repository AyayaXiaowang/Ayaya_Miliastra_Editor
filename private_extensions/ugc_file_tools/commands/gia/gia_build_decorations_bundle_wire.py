from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Optional, Sequence

from ugc_file_tools.beyond_local_export import copy_file_to_beyond_local_export
from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.gia_export.decorations import build_entity_decorations_bundle_wire
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    argument_parser = argparse.ArgumentParser(
        description=(
            "从 decorations_*.report.json 生成“实体类装饰物挂件” .gia（wire-level 保真）。\n"
            "特点：不做语义重编码，仅克隆 base 中现有的装饰物记录并替换必要字段。"
        )
    )
    argument_parser.add_argument("--base-gia", dest="base_gia_file", required=True, help="实体类 base .gia（例如空模型加一个装饰物.gia）")
    argument_parser.add_argument(
        "--decorations-report",
        dest="decorations_report_json",
        required=True,
        help="装饰物报告 JSON（decorations[*].name/template_id/pos/yaw_deg/scale）。",
    )
    argument_parser.add_argument("--output", dest="output_gia_file", required=True, help="输出 .gia（会强制落盘到 ugc_file_tools/out/）")
    argument_parser.add_argument(
        "--limit",
        dest="limit_count",
        type=int,
        default=10,
        help="装饰物数量（默认 10；<=0 表示不限制）。",
    )
    argument_parser.add_argument(
        "--check-header",
        dest="check_header",
        action="store_true",
        help="严格校验 base .gia 容器头/尾（失败会直接抛错）。",
    )
    argument_parser.add_argument(
        "--decode-max-depth",
        dest="decode_max_depth",
        type=int,
        default=16,
        help="保留参数占位（wire 模式不使用；默认 16）。",
    )
    args = argument_parser.parse_args(list(argv) if argv is not None else None)

    out_path = resolve_output_file_path_in_out_dir(Path(args.output_gia_file))
    result = build_entity_decorations_bundle_wire(
        base_gia_path=Path(args.base_gia_file),
        decorations_report_json=Path(args.decorations_report_json),
        output_gia_path=out_path,
        check_header=bool(args.check_header),
        decode_max_depth=int(args.decode_max_depth),
        limit_count=int(args.limit_count),
    )

    output_gia_file = Path(str(result["output_gia_file"])).resolve()
    if not output_gia_file.is_file():
        raise FileNotFoundError(f"生成失败：未找到输出文件：{str(output_gia_file)!r}")
    copied_to: Optional[str] = str(copy_file_to_beyond_local_export(output_gia_file))

    print("=" * 80)
    print("wire decorations bundle 生成完成：")
    print(f"- base_gia_file: {result.get('base_gia_file')}")
    print(f"- output_gia_file: {result.get('output_gia_file')}")
    print(f"- decorations_count: {result.get('decorations_count')}")
    print(f"- unit_id_start: {result.get('unit_id_start')}")
    print(f"- file_path: {result.get('file_path')}")
    print(f"- proto_size: {result.get('proto_size')}")
    print(f"- exported_to: {copied_to}")
    print("=" * 80)


if __name__ == "__main__":
    main()



