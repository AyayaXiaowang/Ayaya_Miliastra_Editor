from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Optional, Sequence

from ugc_file_tools.beyond_local_export import copy_file_to_beyond_local_export
from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.gia_export.wire_patch import patch_gia_file_path_wire
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    argument_parser = argparse.ArgumentParser(
        description=(
            "对 .gia 做保真 wire-level 补丁：只替换 Root.filePath（field_3）。\n"
            "用途：验证“重编码导致真源不可见”的假设。"
        )
    )
    argument_parser.add_argument("--base-gia", dest="base_gia_file", required=True, help="输入 base .gia")
    argument_parser.add_argument("--output", dest="output_gia_file", required=True, help="输出 .gia（会强制落盘到 ugc_file_tools/out/）")
    argument_parser.add_argument("--file-path", dest="new_file_path", required=True, help=r"写入 Root.filePath，例如：<uid>-<time>-<lvl>-\\xxx.gia")
    argument_parser.add_argument(
        "--check-header",
        dest="check_header",
        action="store_true",
        help="严格校验 base .gia 容器头/尾（失败会直接抛错）。",
    )
    args = argument_parser.parse_args(list(argv) if argv is not None else None)

    out_path = resolve_output_file_path_in_out_dir(Path(args.output_gia_file))
    result = patch_gia_file_path_wire(
        base_gia_path=Path(args.base_gia_file),
        output_gia_path=out_path,
        new_file_path=str(args.new_file_path),
        check_header=bool(args.check_header),
    )

    output_gia_file = Path(str(result["output_gia_file"])).resolve()
    if not output_gia_file.is_file():
        raise FileNotFoundError(f"生成失败：未找到输出文件：{str(output_gia_file)!r}")
    copied_to: Optional[str] = str(copy_file_to_beyond_local_export(output_gia_file))

    print("=" * 80)
    print("wire filePath patch 完成：")
    print(f"- base_gia_file: {result.get('base_gia_file')}")
    print(f"- output_gia_file: {result.get('output_gia_file')}")
    print(f"- new_file_path: {result.get('new_file_path')}")
    print(f"- proto_size: {result.get('proto_size')}")
    print(f"- exported_to: {copied_to}")
    print("=" * 80)


if __name__ == "__main__":
    main()



