from __future__ import annotations

import argparse
import os
import sys

from .ugc_converter import UgcConverter


def resolve_default_dtype_path() -> str:
    script_directory = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(
        os.path.join(
            script_directory,
            "..",
            "builtin_resources",
            "dtype",
            "dtype.json",
        )
    )


def main() -> None:
    argument_parser = argparse.ArgumentParser(
        description="Genshin Impact UGC .gil/.gia → .json 轉換（Python 版，僅解碼）"
    )
    argument_parser.add_argument("input_path", help="輸入文件路徑（.gil 或 .gia）")
    argument_parser.add_argument(
        "-d",
        "--decode",
        action="store_true",
        help="強制使用解碼模式（默認根據擴展名自動判斷）",
    )
    argument_parser.add_argument(
        "-e",
        "--encode",
        action="store_true",
        help="編碼模式（當前 Python 版本暫未實現）",
    )
    argument_parser.add_argument(
        "-o",
        "--output",
        dest="output_path",
        help="輸出 JSON 文件路徑（默認為 output.json）",
    )
    argument_parser.add_argument(
        "-t",
        "--dtype",
        dest="dtype_path",
        help="dtype.json 路徑（默認為 ugc_file_tools/builtin_resources/dtype/dtype.json）",
    )

    arguments = argument_parser.parse_args()

    input_path = arguments.input_path
    decode_mode = arguments.decode
    encode_mode = arguments.encode
    output_path = arguments.output_path
    dtype_path = arguments.dtype_path

    if not decode_mode and not encode_mode:
        _, extension = os.path.splitext(input_path)
        if extension.lower() == ".json":
            encode_mode = True
        else:
            decode_mode = True

    if encode_mode:
        print("當前 Python 版本暫未實現編碼功能（json → gil/gia）。", file=sys.stderr)
        sys.exit(1)

    if not decode_mode:
        print("未指定有效模式（解碼或編碼）。", file=sys.stderr)
        sys.exit(1)

    if dtype_path is None:
        dtype_path = resolve_default_dtype_path()

    if output_path is None:
        output_path = "output.json"

    converter = UgcConverter()
    converter.load_dtype(dtype_path)
    converter.load_file(input_path)
    converter.save_json(output_path)


if __name__ == "__main__":
    main()


