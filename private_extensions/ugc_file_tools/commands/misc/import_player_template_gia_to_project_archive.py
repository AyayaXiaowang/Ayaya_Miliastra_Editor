from __future__ import annotations

"""
import_player_template_gia_to_project_archive.py

目标：
- 将“玩家模板 .gia”导入到 Graph_Generater 项目存档：
  - 生成/覆盖 `战斗预设/玩家模板/*.json`
  - 生成/覆盖 `管理配置/关卡变量/自定义变量/*.py`（VARIABLE_FILE_ID + LEVEL_VARIABLES）

说明：
- 当前聚焦：玩家模板身上的自定义变量（override variables group1）必须被完整保留；
- 该工具不会尝试反推完整战斗预设字段（职业/技能/节点图挂载等），只生成一个可编辑的最小模板 JSON 骨架。
"""

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from ugc_file_tools.console_encoding import configure_console_encoding


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(description="玩家模板 .gia → 导入到项目存档（生成玩家模板 JSON + 变量文件）。")
    parser.add_argument("--input-gia", required=True, help="输入玩家模板 .gia 文件路径。")
    parser.add_argument("--project-root", required=True, help="目标项目存档根目录路径。")
    parser.add_argument("--overwrite", action="store_true", help="允许覆盖已存在的输出文件（谨慎）。")
    parser.add_argument("--output-variable-file-id", default="", help="可选：覆盖输出变量文件 VARIABLE_FILE_ID。")
    parser.add_argument("--output-variable-file-name", default="", help="可选：覆盖输出变量文件 VARIABLE_FILE_NAME。")
    parser.add_argument("--output-template-id", default="", help="可选：覆盖输出玩家模板 JSON 的 template_id。")
    parser.add_argument("--report", dest="report_json", default="", help="可选：将导入 report 写入 JSON 文件。")

    args = parser.parse_args(list(argv) if argv is not None else None)

    input_gia = Path(str(args.input_gia)).resolve()
    project_root = Path(str(args.project_root)).resolve()
    report_json_text = str(args.report_json or "").strip()
    report_json_path = Path(report_json_text).resolve() if report_json_text else None

    from ugc_file_tools.pipelines.player_template_gia_to_project_archive import (
        ImportPlayerTemplateGiaPlan,
        run_import_player_template_gia_to_project_archive,
    )

    plan = ImportPlayerTemplateGiaPlan(
        input_gia_file=input_gia,
        project_archive_path=project_root,
        overwrite=bool(args.overwrite),
        output_variable_file_id=str(args.output_variable_file_id or "").strip(),
        output_variable_file_name=str(args.output_variable_file_name or "").strip(),
        output_template_id=str(args.output_template_id or "").strip(),
    )
    report = run_import_player_template_gia_to_project_archive(plan=plan)

    if report_json_path is not None:
        report_json_path.parent.mkdir(parents=True, exist_ok=True)
        report_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 80)
    print("玩家模板 .gia → 导入项目存档 完成：")
    for k in sorted(report.keys()):
        print(f"- {k}: {report.get(k)}")
    print("=" * 80)


if __name__ == "__main__":
    main()



