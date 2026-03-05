from __future__ import annotations

"""
import_gia_templates_and_instances_to_project_archive.py

目标：
- 将一个“元件模板 + 装饰物/实体实例”的 `.gia` 包导入到 Graph_Generater 项目存档目录：
  - `元件库/*.json` + `元件库/templates_index.json`
  - `实体摆放/*.json` + `实体摆放/instances_index.json`
"""

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from ugc_file_tools.console_encoding import configure_console_encoding


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(
        description="导入“元件模板+实体摆放”的 .gia 到项目存档（生成 TemplateConfig/InstanceConfig JSON + 索引）。"
    )
    parser.add_argument("--input-gia", required=True, help="输入 .gia 文件路径。")
    parser.add_argument("--project-root", required=True, help="目标项目存档根目录路径（例如 assets/资源库/项目存档/<package_id>）。")
    parser.add_argument("--overwrite", action="store_true", help="允许覆盖已存在的 template_id/instance_id（谨慎）。")
    parser.add_argument("--skip-templates", action="store_true", help="跳过导入元件库（仅导入实体摆放；要求目标已存在被引用模板）。")
    parser.add_argument("--skip-instances", action="store_true", help="跳过导入实体摆放（仅导入元件库）。")
    parser.add_argument(
        "--instances-mode",
        choices=["decorations_to_template", "decorations_carrier", "instances"],
        default="decorations_to_template",
        help=(
            "实体/装饰物导入模式：\n"
            "- decorations_to_template：将 Root.field_2 按被引用 template_id 分组，写入到对应元件模板的 metadata.common_inspector.model.decorations（以元件为主；不生成实体摆放文件）\n"
            "- decorations_carrier：将 Root.field_2 合并为 1 个“装饰物载体实体”，写入 metadata.common_inspector.model.decorations（推荐）\n"
            "- instances：Root.field_2 每个 unit 生成 1 个 实体摆放/*.json（旧行为，可能产生大量文件）"
        ),
    )
    parser.add_argument(
        "--decorations-carrier-template-id",
        default="",
        help="可选：decorations_carrier 模式下，显式指定载体模板 template_id（必须为十进制整数文本）。",
    )
    parser.add_argument(
        "--decorations-carrier-template-name",
        default="",
        help="可选：decorations_carrier 模式下，显式指定载体模板名称（留空则自动生成）。",
    )
    parser.add_argument(
        "--decorations-carrier-instance-id",
        default="",
        help="可选：decorations_carrier 模式下，显式指定载体实体 instance_id（必须为十进制整数文本）；decorations_to_template 下忽略。",
    )
    parser.add_argument(
        "--decorations-carrier-instance-name",
        default="",
        help="可选：decorations_carrier 模式下，显式指定载体实体名称（留空则自动生成）；decorations_to_template 下忽略。",
    )
    parser.add_argument("--decode-max-depth", type=int, default=28, help="protobuf 递归解码深度上限（默认 28）。")
    parser.add_argument("--report", dest="report_json", default="", help="可选：将导入 report 写入 JSON 文件。")

    args = parser.parse_args(list(argv) if argv is not None else None)

    input_gia = Path(str(args.input_gia)).resolve()
    project_root = Path(str(args.project_root)).resolve()
    report_json_text = str(args.report_json or "").strip()
    report_json_path = Path(report_json_text).resolve() if report_json_text else None

    from ugc_file_tools.pipelines.gia_templates_and_instances_to_project_archive import (
        ImportGiaTemplatesAndInstancesPlan,
        run_import_gia_templates_and_instances_to_project_archive,
    )

    plan = ImportGiaTemplatesAndInstancesPlan(
        input_gia_file=input_gia,
        project_archive_path=project_root,
        overwrite=bool(args.overwrite),
        decode_max_depth=int(args.decode_max_depth),
        skip_templates=bool(args.skip_templates),
        skip_instances=bool(args.skip_instances),
        instances_mode=str(args.instances_mode or "decorations_carrier"),
        decorations_carrier_template_id=str(args.decorations_carrier_template_id or "").strip(),
        decorations_carrier_template_name=str(args.decorations_carrier_template_name or "").strip(),
        decorations_carrier_instance_id=str(args.decorations_carrier_instance_id or "").strip(),
        decorations_carrier_instance_name=str(args.decorations_carrier_instance_name or "").strip(),
    )
    report = run_import_gia_templates_and_instances_to_project_archive(plan=plan)

    if report_json_path is not None:
        report_json_path.parent.mkdir(parents=True, exist_ok=True)
        report_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 80)
    print("导入 .gia → 项目存档 完成：")
    for k in sorted(report.keys()):
        print(f"- {k}: {report.get(k)}")
    print("=" * 80)


if __name__ == "__main__":
    main()


