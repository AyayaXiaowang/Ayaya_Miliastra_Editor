from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Optional, Sequence

from ugc_file_tools.beyond_local_export import copy_file_to_beyond_local_export
from ugc_file_tools.beyond_local_export import get_beyond_local_export_dir
from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.gia_export.decorations import build_decorations_bundle_gia


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    argument_parser = argparse.ArgumentParser(
        description=(
            "从 decorations_*.report.json 生成“装饰物挂件类” .gia（纯 Python）。\n"
            "说明：本工具会以 base .gia 作为“结构模板”（保留其 parent(GraphUnit) payload 细节），"
            "并克隆其第一个装饰物 unit 作为模板批量生成 N 个装饰物。"
        )
    )
    argument_parser.add_argument("--base-gia", dest="base_gia_file", required=True, help="结构模板 base .gia（例如控模型带内容.gia）")
    argument_parser.add_argument(
        "--decorations-report",
        dest="decorations_report_json",
        required=True,
        help="装饰物抽取报告 JSON（包含 decorations[*].name/template_id/pos/yaw_deg/scale）",
    )
    argument_parser.add_argument("--output", dest="output_gia_file", required=True, help="输出 .gia 路径（会强制落盘到 ugc_file_tools/out/）")
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
        help="protobuf 递归解码深度上限（默认 16）。",
    )
    argument_parser.add_argument(
        "--parent-name",
        dest="parent_name_override",
        default="",
        help="覆盖 parent(GraphUnit) 的名称；留空则默认可从 report.parent_struct.name 读取。",
    )
    argument_parser.add_argument(
        "--no-use-report-parent-name",
        dest="use_report_parent_name",
        action="store_false",
        help="禁用从 report.parent_struct.name 自动填充 parent_name（仅当 --parent-name 为空时生效）。",
    )
    argument_parser.add_argument(
        "--file-path",
        dest="file_path_override",
        default="",
        help="覆盖 Root.filePath 字段（留空则保留 base 的 filePath）。",
    )
    argument_parser.add_argument(
        "--game-version",
        dest="game_version_override",
        default="",
        help="覆盖 Root.gameVersion 字段（留空则保留 base 的版本）。",
    )
    argument_parser.add_argument(
        "--copy-to",
        dest="copy_to_dir",
        default="",
        help="可选：生成后复制到指定目录（例如 Beyond_Local_Export）。",
    )
    argument_parser.add_argument(
        "--copy-to-beyond-export",
        dest="copy_to_beyond_export",
        action="store_true",
        help="可选：生成后复制到默认 Beyond_Local_Export（由 Path.home()/AppData/LocalLow/... 推导）。",
    )

    args = argument_parser.parse_args(list(argv) if argv is not None else None)

    result = build_decorations_bundle_gia(
        base_gia_path=Path(args.base_gia_file),
        decorations_report_json=Path(args.decorations_report_json),
        output_gia_path=Path(args.output_gia_file),
        check_header=bool(args.check_header),
        decode_max_depth=int(args.decode_max_depth),
        parent_name_override=str(args.parent_name_override or ""),
        file_path_override=str(args.file_path_override or ""),
        game_version_override=str(args.game_version_override or ""),
        use_report_parent_name=bool(args.use_report_parent_name),
    )

    output_gia_file = Path(str(result.get("output_gia_file") or "")).resolve()
    if not output_gia_file.is_file():
        raise FileNotFoundError(f"生成失败：未找到输出文件：{str(output_gia_file)!r}")

    exported_to = str(copy_file_to_beyond_local_export(output_gia_file))

    copy_to_dir_text = str(args.copy_to_dir or "").strip()
    if bool(args.copy_to_beyond_export):
        copy_to_dir_text = str(get_beyond_local_export_dir())

    copied_to: Optional[str] = None
    if copy_to_dir_text != "":
        copy_to_dir = Path(copy_to_dir_text).resolve()
        copy_to_dir.mkdir(parents=True, exist_ok=True)
        copied_path = copy_to_dir / output_gia_file.name
        shutil.copy2(output_gia_file, copied_path)
        copied_to = str(copied_path)

    print("=" * 80)
    print("GIA 生成完成：")
    print(f"- base_gia_file: {result.get('base_gia_file')}")
    print(f"- output_gia_file: {result.get('output_gia_file')}")
    print(f"- decorations_count: {result.get('decorations_count')}")
    print(f"- parent_struct_id: {result.get('parent_struct_id')}")
    print(f"- parent_name: {result.get('parent_name')}")
    print(f"- file_path: {result.get('file_path')}")
    print(f"- game_version: {result.get('game_version')}")
    print(f"- exported_to: {exported_to}")
    if copied_to:
        print(f"- copied_to: {copied_to}")
    print("=" * 80)


if __name__ == "__main__":
    main()



