from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Optional, Sequence

from ugc_file_tools.beyond_local_export import copy_file_to_beyond_local_export
from ugc_file_tools.beyond_local_export import get_beyond_local_export_dir
from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.gia.wire_preview_pack_processor import process_preview_entities_in_pack_wire
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(
        description=(
            "对“打包 .gia”内的一组预览实体做 wire-level 处理：\n"
            "- 按 name_contains 过滤 parent（必须带 relatedIds）\n"
            "- 按 level_regex 提取关卡 key，同关可合并为一个 parent（relatedIds 并集）\n"
            "- 将 parent 放到装饰物中心，然后整体平移使 parent 到原点 (0,0,0)\n"
            "注意：该工具是 best-effort，适用于“GraphUnit + relatedIds + transform”形态；不保证覆盖所有 .gia 资产类型。"
        )
    )
    parser.add_argument("--input-gia", required=True, help="输入 .gia 文件路径")
    parser.add_argument("--output", required=True, help="输出 .gia（强制落盘到 ugc_file_tools/out/）")
    parser.add_argument("--check-header", action="store_true", help="严格校验 .gia 容器头/尾。")

    parser.add_argument("--name-contains", default="预览实体", help="筛选 parent 的 name 子串（默认：预览实体）。")
    parser.add_argument("--center-mode", choices=["bbox", "mean"], default="bbox", help="中心点计算方式：bbox 或 mean。")
    parser.add_argument(
        "--level-regex",
        default=r"第[一二三四五六七八九十百千0-9]+关",
        help=r"从 parent.name 提取“关卡 key”的正则（默认：第[一二三四五六七八九十百千0-9]+关）。匹配失败则以 name 作为 key（避免误合并）。",
    )
    parser.add_argument("--no-merge", dest="merge_same_level", action="store_false", help="禁用同关合并。")
    parser.add_argument(
        "--drop-other-parents",
        action="store_true",
        help="同关合并后删除其它 parent（默认只清空它们的 relatedIds）。",
    )
    parser.add_argument(
        "--entityize",
        action="store_true",
        help="将匹配到的 parent GraphUnit 实体化：对齐真源“实体导出.gia”，补丁为 type=2, which=3（仍保持当前打包 .gia 结构，不走项目存档导入）。",
    )

    parser.add_argument("--keep-file-path", action="store_true", help="保持 Root.filePath 不变。")
    parser.add_argument("--file-path", default="", help=r"覆盖 Root.filePath（例如 <uid>-<time>-<lvl>-\\xxx.gia）。")

    parser.add_argument("--copy-to", default="", help="可选：生成后复制到指定目录。")
    parser.add_argument("--copy-to-beyond-export", action="store_true", help="可选：复制到默认 Beyond_Local_Export。")
    parser.add_argument("--report", default="", help="可选：输出 report.json（强制落盘到 out/）。")

    args = parser.parse_args(list(argv) if argv is not None else None)

    output_path = resolve_output_file_path_in_out_dir(Path(args.output), default_file_name="preview_processed.gia")
    report_path: Optional[Path] = None
    if str(args.report or "").strip() != "":
        report_path = resolve_output_file_path_in_out_dir(Path(args.report), default_file_name="gia_process_preview_entities_in_pack.report.json")

    result = process_preview_entities_in_pack_wire(
        input_gia_path=Path(args.input_gia).resolve(),
        output_gia_path=Path(output_path).resolve(),
        check_header=bool(args.check_header),
        name_contains=str(args.name_contains or "").strip(),
        center_mode=str(args.center_mode),
        level_regex=str(args.level_regex),
        merge_same_level=bool(args.merge_same_level),
        drop_other_parents=bool(args.drop_other_parents),
        entityize_parents=bool(args.entityize),
        keep_file_path=bool(args.keep_file_path) and (str(args.file_path or "").strip() == ""),
        file_path_override=str(args.file_path or "").strip(),
    )

    output_gia_file = Path(str(result.get("output_gia_file") or "")).resolve()
    if not output_gia_file.is_file():
        raise FileNotFoundError(f"生成失败：未找到输出文件：{str(output_gia_file)!r}")

    exported_to = str(copy_file_to_beyond_local_export(output_gia_file))

    copy_to_dir_text = str(args.copy_to or "").strip()
    if bool(args.copy_to_beyond_export):
        copy_to_dir_text = str(get_beyond_local_export_dir())
    copied_to: Optional[str] = None
    if copy_to_dir_text != "":
        copy_to_dir = Path(copy_to_dir_text).resolve()
        copy_to_dir.mkdir(parents=True, exist_ok=True)
        copied_path = copy_to_dir / output_gia_file.name
        shutil.copy2(output_gia_file, copied_path)
        copied_to = str(copied_path)

    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_obj = {**dict(result), "exported_to": exported_to, "copied_to": copied_to}
        report_path.write_text(json.dumps(report_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 80)
    print("预览实体处理完成：")
    for k in sorted(result.keys()):
        print(f"- {k}: {result.get(k)}")
    print(f"- exported_to: {exported_to}")
    if copied_to:
        print(f"- copied_to: {copied_to}")
    if report_path is not None:
        print(f"- report_json: {str(report_path)}")
    print("=" * 80)


if __name__ == "__main__":
    main()

