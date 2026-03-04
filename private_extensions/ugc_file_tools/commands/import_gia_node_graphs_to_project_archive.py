from __future__ import annotations

"""
import_gia_node_graphs_to_project_archive.py

目标：
- 将一个包含 NodeGraph GraphUnits 的 `.gia` 文件导入到 Graph_Generater 项目存档目录：
  - 生成 `节点图/<server|client>/*.py`（Graph Code）
  - 可选：导入后执行项目存档校验（引擎 ComprehensiveValidator）
"""

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from ugc_file_tools.console_encoding import configure_console_encoding


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(
        description="导入 `.gia` NodeGraph 到项目存档（生成 Graph Code，并可选执行综合校验）。"
    )
    parser.add_argument("--input-gia", required=True, help="输入 .gia 文件路径（节点图 .gia）。")
    parser.add_argument("--project-root", required=True, help="目标项目存档根目录路径（例如 assets/资源库/项目存档/<package_id>）。")
    parser.add_argument("--package-id", required=True, help="目标项目存档 ID（用于校验与 package_state）。")
    parser.add_argument("--overwrite", action="store_true", help="允许覆盖已存在的节点图 Graph Code（谨慎）。")
    parser.add_argument("--check-header", action="store_true", help="严格校验 .gia 容器头/尾（失败会直接抛错）。")
    parser.add_argument("--max-depth", type=int, default=32, help="protobuf 递归解码深度上限（默认 32）。")
    parser.add_argument("--skip-validate", action="store_true", help="跳过导入后综合校验（更快，但不保证可用）。")
    parser.add_argument("--set-last-opened", action="store_true", help="导入成功后设置为最近打开存档（写入 app/runtime/package_state.json）。")
    parser.add_argument("--report", dest="report_json", default="", help="可选：将导入 report 写入 JSON 文件。")

    args = parser.parse_args(list(argv) if argv is not None else None)

    input_gia = Path(str(args.input_gia)).resolve()
    project_root = Path(str(args.project_root)).resolve()
    package_id = str(args.package_id or "").strip()
    if package_id == "":
        raise ValueError("package_id 不能为空")

    report_json_text = str(args.report_json or "").strip()
    report_json_path = Path(report_json_text).resolve() if report_json_text else None

    from ugc_file_tools.pipelines.gia_node_graphs_to_project_archive import (
        ImportGiaNodeGraphsPlan,
        run_import_gia_node_graphs_to_project_archive,
    )

    plan = ImportGiaNodeGraphsPlan(
        input_gia_file=input_gia,
        project_archive_path=project_root,
        package_id=package_id,
        overwrite_graph_code=bool(args.overwrite),
        check_header=bool(args.check_header),
        decode_max_depth=int(args.max_depth),
        validate_after_import=(not bool(args.skip_validate)),
        set_last_opened=bool(args.set_last_opened),
    )
    report = run_import_gia_node_graphs_to_project_archive(plan=plan)

    if report_json_path is not None:
        report_json_path.parent.mkdir(parents=True, exist_ok=True)
        report_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 80)
    print("导入 .gia NodeGraph → 项目存档 完成：")
    for k in sorted(report.keys()):
        print(f"- {k}: {report.get(k)}")
    print("=" * 80)


if __name__ == "__main__":
    main()

