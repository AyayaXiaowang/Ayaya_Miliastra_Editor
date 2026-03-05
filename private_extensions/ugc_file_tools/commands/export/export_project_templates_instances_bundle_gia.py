from __future__ import annotations

"""
export_project_templates_instances_bundle_gia.py

项目存档 → 导出“元件模板+实体摆放(装饰物实例)” bundle.gia（按模板逐个切片导出）。

说明：
- 该工具是“保真导出”路径：依赖模板 JSON 的 `metadata.ugc.source_gia_file` 与 `source_template_root_id_int`，
  从真源 bundle.gia 中 wire-level 切片导出。
- 若模板不是由 .gia 导入（缺少 source 字段），该工具会直接报错；请改用 `export_project_templates_to_gia`
  导出“空模型元件模板（仅自定义变量/占位）”。
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from ugc_file_tools.beyond_local_export import get_beyond_local_export_dir
from ugc_file_tools.console_encoding import configure_console_encoding


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(
        description="项目存档 → 导出 bundle.gia（Root.field_1 templates + Root.field_2 instances；按模板逐个切片导出；产物落盘到 ugc_file_tools/out/）。"
    )
    parser.add_argument("--project-root", required=True, help="项目存档根目录路径（例如 assets/资源库/项目存档/测试项目）。")
    parser.add_argument(
        "--template-json",
        dest="template_json_files",
        action="append",
        default=[],
        help="可选：仅导出指定元件模板 JSON（可重复传参）；不传则导出当前项目 元件库/*.json。",
    )
    parser.add_argument(
        "--selection-json",
        dest="selection_json",
        default="",
        help="可选：从 JSON 文件读取要导出的模板 JSON 列表（优先级高于 --template-json；用于避免命令行过长）。",
    )
    parser.add_argument(
        "--out-dir",
        dest="output_dir_name_in_out",
        default="",
        help="输出到 ugc_file_tools/out/ 下的子目录名（默认 <package_id>_templates_instances_gia_export）。",
    )
    parser.add_argument(
        "--copy-to",
        dest="output_user_dir",
        default="",
        help="可选：额外复制一份到 out 外的绝对目录（为空则不复制）。",
    )
    parser.add_argument(
        "--copy-to-beyond-export",
        dest="copy_to_beyond_export",
        action="store_true",
        help="可选：生成后复制到默认 Beyond_Local_Export。",
    )
    parser.add_argument(
        "--check-gia-header",
        dest="check_gia_header",
        action="store_true",
        help="可选：对输入 source bundle.gia 做容器头校验（更严格；但会更慢）。",
    )
    parser.add_argument("--report", dest="report_json", default="", help="可选：将导出 report 写入 JSON 文件（便于 UI 调用）。")

    args = parser.parse_args(list(argv) if argv is not None else None)

    project_root = Path(args.project_root).resolve()
    if not project_root.is_dir():
        raise FileNotFoundError(str(project_root))

    template_json_files: list[Path] = []
    selection_json_text = str(getattr(args, "selection_json", "") or "").strip()
    if selection_json_text != "":
        selection_json_path = Path(selection_json_text).resolve()
        if not selection_json_path.is_file():
            raise FileNotFoundError(str(selection_json_path))
        obj = json.loads(selection_json_path.read_text(encoding="utf-8"))
        if not isinstance(obj, list):
            raise TypeError("selection-json 必须为 list[str]")
        for p in [str(x) for x in obj]:
            t = str(p or "").strip()
            if t == "":
                continue
            template_json_files.append(Path(t).resolve())
        if not template_json_files:
            raise ValueError("selection-json 为空：未选择任何模板 JSON")
    else:
        template_json_files = [Path(p).resolve() for p in list(args.template_json_files or []) if str(p).strip() != ""]

    output_user_dir_text = str(args.output_user_dir or "").strip()
    output_user_dir = Path(output_user_dir_text).resolve() if output_user_dir_text else None
    if bool(args.copy_to_beyond_export):
        output_user_dir = Path(get_beyond_local_export_dir()).resolve()

    report_json_text = str(args.report_json or "").strip()
    report_json_path = Path(report_json_text).resolve() if report_json_text else None

    from ugc_file_tools.pipelines.project_export_templates_instances_bundle_gia import (
        ProjectExportTemplatesInstancesBundleGiaPlan,
        run_project_export_templates_instances_bundle_gia,
    )

    out_dir_name = str(args.output_dir_name_in_out or "").strip()
    if out_dir_name == "":
        out_dir_name = f"{project_root.name}_templates_instances_gia_export"

    plan = ProjectExportTemplatesInstancesBundleGiaPlan(
        project_archive_path=project_root,
        template_json_files=(list(template_json_files) if template_json_files else None),
        output_dir_name_in_out=str(out_dir_name),
        output_user_dir=output_user_dir,
        check_gia_header=bool(args.check_gia_header),
    )

    def _progress_cb(current: int, total: int, label: str) -> None:
        print(f"[{int(current)}/{int(total)}] {str(label or '').strip()}", file=sys.stderr, flush=True)

    report = run_project_export_templates_instances_bundle_gia(plan=plan, progress_cb=_progress_cb)

    if report_json_path is not None:
        report_json_path.parent.mkdir(parents=True, exist_ok=True)
        report_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 80)
    print("项目存档 → 导出 bundle.gia 完成：")
    for k in sorted(report.keys()):
        print(f"- {k}: {report.get(k)}")
    print("=" * 80)


if __name__ == "__main__":
    main()

