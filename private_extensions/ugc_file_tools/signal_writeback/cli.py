from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir

from .writer import add_signals_to_gil


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(description="向 .gil 写入“信号定义 + 对应节点定义(3个)”。")
    parser.add_argument("--input-gil", required=True, help="输入 .gil（作为输出容器）")
    parser.add_argument("--output-gil", required=True, help="输出 .gil（强制写入 ugc_file_tools/out/；不要覆盖重要样本）")
    parser.add_argument(
        "--template-gil",
        required=False,
        default="",
        help=(
            "可选：模板 .gil（需要包含至少一个“无参数信号”作为 node_def 基底；"
            "是否还需要“参数类型样本信号”取决于 --param-build-mode）。\n"
            "若不提供：将按 base → bootstrap → 内置默认模板 依次自动选择可用样本。"
        ),
    )
    parser.add_argument(
        "--bootstrap-template-gil",
        required=False,
        default=None,
        help=(
            "可选：自举模板 .gil（用于把“空壳 input-gil”补齐为可导入的完整存档）。"
            "当 input-gil 的 payload 过于精简且缺少大量顶层段时，建议提供一个可导入的空存档作为基底。"
        ),
    )
    parser.add_argument("--spec-json", required=True, help="信号定义 spec.json（见脚本注释）")
    parser.add_argument(
        "--param-build-mode",
        default="semantic",
        choices=["semantic", "template"],
        help="参数口构建模式：semantic=按 type_id 规则构造（不需要模板覆盖每个 type）；template=按模板克隆（需要模板覆盖参数类型）。",
    )
    parser.add_argument(
        "--emit-reserved-placeholder-signal",
        dest="emit_reserved_placeholder_signal",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "当 base `.gil` 完全没有任何信号且选择 0x6000/0x6080 号段时，是否写入“占位无参信号”（常见名："
            "`新建的没有参数的信号`）。\n"
            "关闭该选项时：写回不会把占位信号写入 signal entries / node_defs，但仍会预留掉其应占用的三连号 node_def_id 与首个端口块，"
            "避免第一条业务信号误占用保留槽。"
        ),
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    result = add_signals_to_gil(
        input_gil_file_path=Path(args.input_gil),
        # CLI 约束：强制输出到 ugc_file_tools/out/（避免覆盖重要样本/污染用户目录）。
        output_gil_file_path=resolve_output_file_path_in_out_dir(Path(args.output_gil)),
        template_gil_file_path=(Path(args.template_gil) if str(args.template_gil or "").strip() else None),
        bootstrap_template_gil_file_path=(Path(args.bootstrap_template_gil) if args.bootstrap_template_gil else None),
        spec_json_path=Path(args.spec_json),
        param_build_mode=str(args.param_build_mode),
        emit_reserved_placeholder_signal=bool(args.emit_reserved_placeholder_signal),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()





