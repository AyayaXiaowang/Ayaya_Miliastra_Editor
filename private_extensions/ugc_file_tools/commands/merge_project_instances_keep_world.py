from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.preview_merge.project_instances_merger import merge_project_instances_keep_world


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    argument_parser = argparse.ArgumentParser(
        description=(
            "项目存档工具：合并多个实体摆放实例为一个新实例（keep_world：保持装饰物世界变换不变）。\n"
            "- 输入实例引用的模板 decorations 会被合并到一个新模板；新实例引用该模板。\n"
            "- 默认只 dry-run（不写盘）；需要显式加 --dangerous 才会写入新模板/新实例并重建索引。\n"
        )
    )
    argument_parser.add_argument("--project-root", dest="project_root", required=True, help="项目存档根目录（例如 assets/资源库/项目存档/测试项目）")
    argument_parser.add_argument(
        "--instance-json",
        dest="instance_json_files",
        action="append",
        default=[],
        help="输入 InstanceConfig(JSON) 文件（可重复传参，至少 2 个）。必须位于项目存档 实体摆放/ 下。",
    )
    argument_parser.add_argument("--output-template-name", dest="output_template_name", required=True, help="输出新模板 name（会生成新 template_id 与新 JSON 文件）")
    argument_parser.add_argument("--output-instance-name", dest="output_instance_name", required=True, help="输出新实例 name")
    argument_parser.add_argument("--output-instance-id", dest="output_instance_id", required=True, help="输出新实例 instance_id（字符串）")
    argument_parser.add_argument("--dangerous", dest="dangerous", action="store_true", help="危险写盘：生成新模板/新实例并重建索引。")
    argument_parser.add_argument("--report", dest="report_json", default="", help="可选：输出 report.json（落盘到 ugc_file_tools/out/）。")

    args = argument_parser.parse_args(list(argv) if argv is not None else None)

    result = merge_project_instances_keep_world(
        project_root=Path(args.project_root),
        include_instance_json_files=[Path(x) for x in list(args.instance_json_files or [])],
        output_template_name=str(args.output_template_name or ""),
        output_instance_name=str(args.output_instance_name or ""),
        output_instance_id=str(args.output_instance_id or ""),
        dangerous=bool(args.dangerous),
    )

    report_text = str(args.report_json or "").strip()
    report_path: Optional[Path] = None
    if report_text != "":
        report_path = resolve_output_file_path_in_out_dir(Path(report_text), default_file_name="merge_project_instances_keep_world.report.json")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 80)
    print("实例 keep_world 合并完成：")
    print(f"- project_root: {result.get('project_root')}")
    print(f"- dangerous: {result.get('dangerous')}")
    print(f"- output_template_id: {result.get('output_template_id')}")
    print(f"- output_instance_id: {result.get('output_instance_id')}")
    print(f"- decorations_count: {result.get('decorations_count')}")
    if report_path is not None:
        print(f"- report_json: {str(report_path)}")
    print("=" * 80)


if __name__ == "__main__":
    main()

