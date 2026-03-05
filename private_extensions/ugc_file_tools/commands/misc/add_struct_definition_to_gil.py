from __future__ import annotations

"""
add_struct_definition_to_gil.py

对外入口：
- 统一通过 `python -X utf8 -m ugc_file_tools tool add_struct_definition_to_gil ...` 调用；
- 真实实现已拆分到 `ugc_file_tools/struct_def_writeback/`，避免单文件过长。
"""

import argparse
import json
from pathlib import Path
from typing import Sequence

from ugc_file_tools.struct_def_writeback import *  # noqa: F401,F403


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="向 .gil 存档追加基础结构体定义，并输出新 .gil。")
    parser.add_argument("--input-gil", required=True, help="输入 .gil 文件路径")
    parser.add_argument("--output-gil", required=True, help="输出 .gil 文件名/路径（强制写入 ugc_file_tools/out/）")
    parser.add_argument(
        "--preset",
        default="one-string",
        choices=[
            "one-string",
            "all-types-test",
            "empty-struct",
            "rename-struct",
            "clone-all-supported-base",
            "clone-all-supported-scalars",
            "clone-all-supported-int",
            "clone-all-supported-bool",
            "clone-all-supported-float",
            "clone-all-supported-string",
            "clone-all-supported-vector3",
        ],
        help="生成预设",
    )
    parser.add_argument("--struct-name", required=True, help="结构体名称（显示名）")
    parser.add_argument("--field-name", default="", help="字段名（preset=one-string 时必填）")
    parser.add_argument("--field-default", default="", help="字段默认值（字符串，仅 preset=one-string 使用）")
    parser.add_argument("--struct-id", type=int, default=None, help="结构体配置ID（不填则自动分配）")
    parser.add_argument("--seed", type=int, default=None, help="随机种子（仅 preset=all-types-test 用于随机化部分字段）")
    args = parser.parse_args(argv)

    preset = str(args.preset or "").strip()
    if preset == "one-string":
        if not str(args.field_name).strip():
            raise ValueError("--field-name 不能为空（preset=one-string）")
        report = add_one_string_struct_definition(
            input_gil_file_path=Path(args.input_gil),
            output_gil_file_path=Path(args.output_gil),
            struct_name=args.struct_name,
            field_name=args.field_name,
            field_default=args.field_default,
            struct_id=args.struct_id,
        )
    elif preset == "all-types-test":
        report = add_all_types_test_struct_definition(
            input_gil_file_path=Path(args.input_gil),
            output_gil_file_path=Path(args.output_gil),
            struct_name=args.struct_name,
            struct_id=args.struct_id,
            seed=args.seed,
        )
    elif preset == "empty-struct":
        report = add_empty_struct_definition(
            input_gil_file_path=Path(args.input_gil),
            output_gil_file_path=Path(args.output_gil),
            struct_name=args.struct_name,
            struct_id=args.struct_id,
        )
    elif preset == "rename-struct":
        if args.struct_id is None:
            raise ValueError("--struct-id 不能为空（preset=rename-struct，作为 target_struct_id）")
        report = rename_struct_definition(
            input_gil_file_path=Path(args.input_gil),
            output_gil_file_path=Path(args.output_gil),
            target_struct_id=int(args.struct_id),
            new_struct_name=args.struct_name,
        )
    elif preset == "clone-all-supported-base":
        report = clone_struct_all_supported_definition(
            input_gil_file_path=Path(args.input_gil),
            output_gil_file_path=Path(args.output_gil),
            struct_name=args.struct_name,
            struct_id=args.struct_id,
            profile="base",
        )
    elif preset == "clone-all-supported-scalars":
        report = clone_struct_all_supported_definition(
            input_gil_file_path=Path(args.input_gil),
            output_gil_file_path=Path(args.output_gil),
            struct_name=args.struct_name,
            struct_id=args.struct_id,
            profile="scalars",
        )
    elif preset == "clone-all-supported-int":
        report = clone_struct_all_supported_definition(
            input_gil_file_path=Path(args.input_gil),
            output_gil_file_path=Path(args.output_gil),
            struct_name=args.struct_name,
            struct_id=args.struct_id,
            profile="int",
        )
    elif preset == "clone-all-supported-bool":
        report = clone_struct_all_supported_definition(
            input_gil_file_path=Path(args.input_gil),
            output_gil_file_path=Path(args.output_gil),
            struct_name=args.struct_name,
            struct_id=args.struct_id,
            profile="bool",
        )
    elif preset == "clone-all-supported-float":
        report = clone_struct_all_supported_definition(
            input_gil_file_path=Path(args.input_gil),
            output_gil_file_path=Path(args.output_gil),
            struct_name=args.struct_name,
            struct_id=args.struct_id,
            profile="float",
        )
    elif preset == "clone-all-supported-string":
        report = clone_struct_all_supported_definition(
            input_gil_file_path=Path(args.input_gil),
            output_gil_file_path=Path(args.output_gil),
            struct_name=args.struct_name,
            struct_id=args.struct_id,
            profile="string",
        )
    elif preset == "clone-all-supported-vector3":
        report = clone_struct_all_supported_definition(
            input_gil_file_path=Path(args.input_gil),
            output_gil_file_path=Path(args.output_gil),
            struct_name=args.struct_name,
            struct_id=args.struct_id,
            profile="vector3",
        )
    else:
        raise ValueError(f"unknown preset: {preset!r}")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()



