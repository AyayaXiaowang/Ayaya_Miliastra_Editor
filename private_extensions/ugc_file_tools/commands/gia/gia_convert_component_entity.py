from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Optional, Sequence, Tuple

from ugc_file_tools.beyond_local_export import copy_file_to_beyond_local_export
from ugc_file_tools.beyond_local_export import get_beyond_local_export_dir
from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.gia_export.templates_instances import convert_component_entity_bundle_gia_wire
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir


def _parse_vec3(text: str, *, default: Tuple[float, float, float]) -> Tuple[float, float, float]:
    raw = str(text or "").strip()
    if raw == "":
        return (float(default[0]), float(default[1]), float(default[2]))
    parts = [p.strip() for p in raw.replace("，", ",").split(",")]
    if len(parts) != 3:
        raise ValueError(f"vec3 必须为 'x,y,z'：{text!r}")
    return (float(parts[0]), float(parts[1]), float(parts[2]))


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(
        description=(
            "对“元件模板+实体摆放(实例)”类 bundle.gia 做 wire-level 转换：\n"
            "- component_to_entity：从 Root.field_1(templates) 生成 Root.field_2(instances)\n"
            "- entity_to_component：清空 Root.field_2，并按引用裁剪 Root.field_1(templates)\n"
            "说明：该工具只适用于该 bundle 形态（不是 accessories 装饰物挂件那类 .gia）。"
        )
    )
    parser.add_argument("--input-gia", required=True, help="输入 bundle.gia")
    parser.add_argument("--output", required=True, help="输出 .gia（强制落盘到 ugc_file_tools/out/）")
    parser.add_argument("--check-header", action="store_true", help="严格校验 .gia 容器头/尾。")

    parser.add_argument(
        "--mode",
        choices=["component_to_entity", "entity_to_component"],
        required=True,
        help="转换方向：元件→实体 或 实体→元件。",
    )

    # entity_to_component options
    parser.add_argument(
        "--keep-unreferenced-templates",
        action="store_true",
        help="实体→元件时：保留未被实例引用的 templates（默认只保留被引用闭包）。",
    )

    # component_to_entity options
    parser.add_argument(
        "--template-name-contains",
        default="",
        help="元件→实体时：仅为 name 包含该子串的模板生成实例（默认空=全量模板）。",
    )
    parser.add_argument(
        "--drop-existing-instances",
        action="store_true",
        help="元件→实体时：丢弃输入中已有的 instances（Root.field_2），只输出新生成的实例。",
    )
    parser.add_argument(
        "--instance-template-gia",
        default="",
        help="元件→实体时：当输入内没有 Root.field_2 实例可克隆时，提供一个含实例的真源 bundle.gia 作为结构模板。",
    )
    parser.add_argument(
        "--pos-mode",
        choices=["origin", "grid"],
        default="grid",
        help="元件→实体时：生成实例的摆放方式：origin(全部同点) 或 grid(按步长平铺)。默认 grid。",
    )
    parser.add_argument("--start-pos", default="0,0,0", help="元件→实体时：起始位置 'x,y,z'（默认 0,0,0）。")
    parser.add_argument("--grid-step", default="200,0,0", help="元件→实体时：grid 步长 'x,y,z'（默认 200,0,0）。")
    parser.add_argument("--default-rot-deg", default="0,0,0", help="元件→实体时：默认旋转角度(deg) 'x,y,z'（默认 0,0,0）。")
    parser.add_argument("--default-scale", default="1,1,1", help="元件→实体时：默认缩放 'x,y,z'（默认 1,1,1）。")

    # filePath
    parser.add_argument("--keep-file-path", action="store_true", help="保持 Root.filePath 不变。")
    parser.add_argument("--file-path", default="", help=r"覆盖 Root.filePath（例如 <uid>-<time>-<lvl>-\\xxx.gia）。")

    # copy/report
    parser.add_argument("--copy-to", default="", help="可选：生成后复制到指定目录。")
    parser.add_argument("--copy-to-beyond-export", action="store_true", help="可选：复制到默认 Beyond_Local_Export。")
    parser.add_argument("--report", default="", help="可选：输出 report.json（强制落盘到 out/）。")

    args = parser.parse_args(list(argv) if argv is not None else None)

    output_path = resolve_output_file_path_in_out_dir(Path(args.output), default_file_name="converted_bundle.gia")
    report_path: Optional[Path] = None
    report_text = str(args.report or "").strip()
    if report_text != "":
        report_path = resolve_output_file_path_in_out_dir(Path(report_text), default_file_name="gia_convert_component_entity.report.json")

    instance_template_gia_path: Optional[Path] = None
    instance_template_text = str(args.instance_template_gia or "").strip()
    if instance_template_text != "":
        instance_template_gia_path = Path(instance_template_text).resolve()

    result = convert_component_entity_bundle_gia_wire(
        input_gia_path=Path(args.input_gia).resolve(),
        output_gia_path=Path(output_path).resolve(),
        check_header=bool(args.check_header),
        mode=str(args.mode),
        keep_file_path=bool(args.keep_file_path) and (str(args.file_path or "").strip() == ""),
        file_path_override=str(args.file_path or "").strip(),
        keep_unreferenced_templates=bool(args.keep_unreferenced_templates),
        instance_template_gia_path=instance_template_gia_path,
        template_name_contains=str(args.template_name_contains or "").strip(),
        drop_existing_instances=bool(args.drop_existing_instances),
        pos_mode=str(args.pos_mode),
        grid_step=_parse_vec3(str(args.grid_step), default=(200.0, 0.0, 0.0)),
        start_pos=_parse_vec3(str(args.start_pos), default=(0.0, 0.0, 0.0)),
        default_rot_deg=_parse_vec3(str(args.default_rot_deg), default=(0.0, 0.0, 0.0)),
        default_scale=_parse_vec3(str(args.default_scale), default=(1.0, 1.0, 1.0)),
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
    print("GIA 元件/实体 转换完成：")
    print(f"- input_gia_file: {result.get('input_gia_file')}")
    print(f"- output_gia_file: {result.get('output_gia_file')}")
    print(f"- mode: {result.get('mode')}")
    print(f"- templates: {result.get('templates_in')} -> {result.get('templates_out')}")
    print(f"- instances: {result.get('instances_in')} -> {result.get('instances_out')}")
    print(f"- file_path: {result.get('file_path')}")
    print(f"- exported_to: {exported_to}")
    if copied_to:
        print(f"- copied_to: {copied_to}")
    if report_path is not None:
        print(f"- report_json: {str(report_path)}")
    print("=" * 80)


if __name__ == "__main__":
    main()

