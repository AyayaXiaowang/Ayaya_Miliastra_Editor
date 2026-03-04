from __future__ import annotations

import argparse
from pathlib import Path

from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir

def _command_entity_qrcode(arguments: argparse.Namespace) -> None:
    # 收敛：二维码实体 `.gia` 生成已迁移为可 import 的实现，
    # 不再依赖 `UGC-File-Generate-Utils` 的 sys.path 注入与松散顶层模块导入。
    from ugc_file_tools.gia_export.qrcode_entity import write_qrcode_entity_gia_file

    output_gia_path = resolve_output_file_path_in_out_dir(Path(arguments.output_gia_file))
    write_qrcode_entity_gia_file(
        output_gia_path=Path(output_gia_path),
        text=str(arguments.text),
        black_template_id=int(arguments.black_template_id),
        white_template_id=int(arguments.white_template_id),
        global_scale=float(arguments.global_scale),
        start_position_x=float(arguments.start_position_x),
        start_position_y=float(arguments.start_position_y),
        start_position_z=float(arguments.start_position_z),
        entity_id_start=int(arguments.entity_id_start),
    )


def add_subparser_entity(subparsers: argparse._SubParsersAction) -> None:
    entity_parser = subparsers.add_parser("entity", help="生成/修改 .gia 实体文件相关功能")
    entity_subparsers = entity_parser.add_subparsers(dest="entity_command", required=True)

    qrcode_parser = entity_subparsers.add_parser("qrcode", help="从字符串生成二维码方块墙（输出 .gia）")
    qrcode_parser.add_argument("--text", required=True, help="要编码的字符串")
    qrcode_parser.add_argument("--output", dest="output_gia_file", required=True, help="输出 .gia 文件路径")
    qrcode_parser.add_argument(
        "--black-template-id",
        dest="black_template_id",
        type=int,
        default=20002121,
        help="黑色方块模板ID",
    )
    qrcode_parser.add_argument(
        "--white-template-id",
        dest="white_template_id",
        type=int,
        default=20002146,
        help="白色方块模板ID",
    )
    qrcode_parser.add_argument("--global-scale", dest="global_scale", type=float, default=1.0, help="全局缩放")
    qrcode_parser.add_argument("--start-x", dest="start_position_x", type=float, default=0.0, help="起始位置 X")
    qrcode_parser.add_argument("--start-y", dest="start_position_y", type=float, default=0.0, help="起始位置 Y")
    qrcode_parser.add_argument("--start-z", dest="start_position_z", type=float, default=0.0, help="起始位置 Z")
    qrcode_parser.add_argument("--entity-id-start", dest="entity_id_start", type=int, default=1078000000, help="起始实体ID")
    qrcode_parser.set_defaults(entrypoint=_command_entity_qrcode)


