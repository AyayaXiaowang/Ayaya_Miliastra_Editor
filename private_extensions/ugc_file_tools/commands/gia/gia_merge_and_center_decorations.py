from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Optional, Sequence

from ugc_file_tools.beyond_local_export import copy_file_to_beyond_local_export
from ugc_file_tools.beyond_local_export import get_beyond_local_export_dir
from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.gia_export.decorations import merge_and_center_decorations_gia_wire
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    argument_parser = argparse.ArgumentParser(
        description=(
            "对“空物体 + 多装饰物(accessories)”类 .gia 做 wire-level 变换：\n"
            "- 居中：支持两种策略：\n"
            "  - keep_world(默认)：移动空物体(parent)到中心，并反向补偿装饰物 local 坐标，确保装饰物世界坐标不动。\n"
            "  - move_decorations：直接平移装饰物坐标使其围绕原点（会改变装饰物世界坐标）。\n"
            "- 合并：当 Root.field_1 存在多个 parent（带 relatedIds）时，将装饰物统一挂到同一个 parent 上。\n"
            "说明：该工具尽量只改必要字段，避免语义重编码导致真源不可见。"
        )
    )
    argument_parser.add_argument("--input-gia", dest="input_gia_file", required=True, help="输入 .gia 文件路径")
    argument_parser.add_argument("--output", dest="output_gia_file", required=True, help="输出 .gia（会强制落盘到 ugc_file_tools/out/）")
    argument_parser.add_argument(
        "--check-header",
        dest="check_header",
        action="store_true",
        help="严格校验输入 .gia 容器头/尾（失败会直接抛错）。",
    )

    argument_parser.add_argument(
        "--no-center",
        dest="do_center",
        action="store_false",
        help="禁用居中（仅做合并/或仅修正 filePath）。",
    )
    argument_parser.add_argument(
        "--center-mode",
        dest="center_mode",
        choices=["bbox", "mean"],
        default="bbox",
        help="中心点计算方式：bbox(包围盒中心) 或 mean(均值)。默认 bbox。",
    )
    argument_parser.add_argument(
        "--center-axes",
        dest="center_axes",
        choices=["x", "y", "z", "xy", "xz", "yz", "xyz"],
        default="xyz",
        help="居中平移作用的轴：默认 xyz。常用：xz（只水平居中）。",
    )
    argument_parser.add_argument(
        "--center-policy",
        dest="center_policy",
        choices=["keep_world", "move_decorations"],
        default="keep_world",
        help="居中策略：keep_world(默认，装饰物世界坐标不动) 或 move_decorations(直接移动装饰物)。",
    )

    argument_parser.add_argument(
        "--no-merge",
        dest="do_merge",
        action="store_false",
        help="禁用合并（即使 Root.field_1 有多个 parent，也只做居中）。",
    )
    argument_parser.add_argument("--target-parent-id", dest="target_parent_id", type=int, default=None, help="合并目标 parent 的 unit_id（优先级高于 name）。")
    argument_parser.add_argument("--target-parent-name", dest="target_parent_name", default="", help="合并目标 parent 的 GraphUnit.name（需唯一匹配）。")
    argument_parser.add_argument(
        "--drop-other-parents",
        dest="drop_other_parents",
        action="store_true",
        help="合并后删除其它 parent GraphUnit（仅删除“带 relatedIds 的 parent”，不影响其它 GraphUnit）。默认只清空它们的 relatedIds。",
    )

    argument_parser.add_argument(
        "--keep-file-path",
        dest="keep_file_path",
        action="store_true",
        help="保持 Root.filePath 不变（默认会将 filePath 的文件名部分对齐 output 文件名）。",
    )
    argument_parser.add_argument(
        "--file-path",
        dest="file_path_override",
        default="",
        help=r"覆盖 Root.filePath（例如 <uid>-<time>-<lvl>-\\xxx.gia）。优先级高于 --keep-file-path。",
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
    argument_parser.add_argument(
        "--report",
        dest="report_json",
        default="",
        help="可选：输出 report.json（会强制落盘到 ugc_file_tools/out/；用于 UI 集成）。",
    )

    args = argument_parser.parse_args(list(argv) if argv is not None else None)

    output_path = resolve_output_file_path_in_out_dir(Path(args.output_gia_file), default_file_name="decorations_centered.gia")
    result = merge_and_center_decorations_gia_wire(
        input_gia_path=Path(args.input_gia_file),
        output_gia_path=output_path,
        check_header=bool(args.check_header),
        center_mode=str(args.center_mode),
        center_axes=str(args.center_axes),
        center_policy=str(args.center_policy),
        do_center=bool(args.do_center),
        do_merge=bool(args.do_merge),
        target_parent_id=int(args.target_parent_id) if args.target_parent_id is not None else None,
        target_parent_name=str(args.target_parent_name or ""),
        drop_other_parents=bool(args.drop_other_parents),
        keep_file_path=bool(args.keep_file_path) and (str(args.file_path_override or "").strip() == ""),
        file_path_override=str(args.file_path_override or ""),
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

    report_text = str(args.report_json or "").strip()
    report_path: Optional[Path] = None
    if report_text != "":
        report_path = resolve_output_file_path_in_out_dir(Path(report_text), default_file_name="gia_merge_and_center_decorations.report.json")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_obj = {**dict(result), "exported_to": exported_to, "copied_to": copied_to}
        report_path.write_text(json.dumps(report_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 80)
    print("GIA merge/center 完成：")
    print(f"- input_gia_file: {result.get('input_gia_file')}")
    print(f"- output_gia_file: {result.get('output_gia_file')}")
    print(f"- accessories_count: {result.get('accessories_count')}")
    print(f"- merged: {result.get('merged')}")
    print(f"- target_parent_unit_id: {result.get('target_parent_unit_id')}")
    print(f"- center_policy: {result.get('center_policy')} ({result.get('center_space')})")
    print(f"- center: {result.get('center')}")
    print(f"- shift_applied: {result.get('shift_applied')} ({result.get('shift_space')})")
    if result.get("target_parent_pos_before") is not None or result.get("target_parent_pos_after") is not None:
        print(f"- target_parent_pos_before: {result.get('target_parent_pos_before')}")
        print(f"- target_parent_pos_after: {result.get('target_parent_pos_after')}")
    print(f"- file_path: {result.get('file_path')}")
    print(f"- proto_size: {result.get('proto_size')}")
    print(f"- exported_to: {exported_to}")
    if copied_to:
        print(f"- copied_to: {copied_to}")
    if report_path is not None:
        print(f"- report_json: {str(report_path)}")
    print("=" * 80)


if __name__ == "__main__":
    main()

