from __future__ import annotations

"""
export_project_graphs_to_gia.py

目标：
- 从 Graph_Generater 项目存档目录导出节点图为 `.gia`：
  - 默认：每张节点图一个文件；
  - 可选：将多张节点图合并打包为单个 `.gia`（`--pack`）。

说明：
- 复用 `ugc_file_tools/pipelines/project_export_gia.py` 的实现（UI/CLI 同口径）；
- 会按 pipeline 约定将产物写入 `ugc_file_tools/out/<out_dir_name>/`（并可选复制到 out 外目录）。
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from ugc_file_tools.console_encoding import configure_console_encoding


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(
        description="项目存档 → 导出节点图为 .gia（默认每张图一个文件；可选 --pack 合并为单文件）。"
    )
    parser.add_argument(
        "--project-root",
        required=True,
        help="项目存档根目录路径（例如 assets/资源库/项目存档/测试项目）。",
    )
    parser.add_argument(
        "--graph-code",
        dest="graph_code_files",
        action="append",
        default=[],
        help="可选：仅导出指定节点图源码文件（可重复传参）。不传则按 scope + scan_all/overview 导出。",
    )
    parser.add_argument(
        "--graph-source-root",
        dest="graph_source_roots",
        action="append",
        default=[],
        help=(
            "可选：用于稳定分配 graph_id_int 的扫描根目录（可重复传参）。\n"
            "仅当使用 --graph-code 子集导出时有效；不传则默认仅使用 --project-root。"
        ),
    )
    parser.add_argument(
        "--scope",
        dest="graphs_scope",
        default="all",
        choices=["all", "server", "client"],
        help="导出 scope（默认 all）。",
    )
    parser.add_argument(
        "--node-pos-scale",
        dest="node_pos_scale",
        type=float,
        default=2.0,
        help="导出节点图 `.gia` 时节点坐标缩放倍数（对 x/y 同步乘法缩放；默认 2.0）。",
    )
    parser.add_argument(
        "--overview",
        dest="graph_scan_all",
        action="store_false",
        help="使用 <package_id>总览.json 作为图清单（默认 scan_all 扫描 节点图/**.py）。",
    )
    parser.set_defaults(graph_scan_all=True)
    parser.add_argument(
        "--out-dir",
        dest="output_dir_name_in_out",
        default="",
        help="输出到 ugc_file_tools/out/ 下的子目录名（默认 <package_id>_gia_export）。",
    )
    parser.add_argument(
        "--copy-to",
        dest="output_user_dir",
        default="",
        help="可选：额外复制一份到 out 外的绝对目录（为空则不复制）。",
    )
    parser.add_argument(
        "--report",
        dest="report_json",
        default="",
        help="可选：将导出 report 写入 JSON 文件（便于 UI 调用）。",
    )
    parser.add_argument(
        "--allow-unresolved-ui-keys",
        dest="allow_unresolved_ui_keys",
        action="store_true",
        help="允许缺失 UIKey 映射继续导出（缺失的 ui_key 将回填为 0）。",
    )
    parser.add_argument(
        "--ui-export-record",
        dest="ui_export_record",
        default="",
        help=(
            "可选：选择一条“UI 导出记录”用于 ui_key: 占位符回填（更可控，默认建议）。\n"
            "- 传 record_id：使用该记录绑定的 ui_guid_registry 快照；\n"
            "- 传 latest：使用当前项目最新的一条记录；\n"
            "- 留空：优先自动选择最新记录；若不存在记录则使用当前 ui_guid_registry.json（项目/运行时缓存）。"
        ),
    )
    parser.add_argument(
        "--base-gil-for-signal-defs",
        dest="base_gil_for_signal_defs",
        default="",
        help="可选：提供 base .gil，用于导出时读取信号定义表，避免信号节点导入后串号。",
    )
    parser.add_argument(
        "--id-ref-gil",
        dest="id_ref_gil_file",
        default="",
        help="可选：占位符参考 `.gil` 文件，用于回填节点图中的 entity_key/component_key（按名称匹配，取第一个）。",
    )
    parser.add_argument(
        "--id-ref-overrides-json",
        dest="id_ref_overrides_json_file",
        default="",
        help="可选：entity_key/component_key 占位符手动覆盖映射 JSON（占位符 name → ID）。",
    )
    parser.add_argument(
        "--inject-target-gil",
        dest="inject_target_gil_file",
        default="",
        help="可选：导出完成后将 NodeGraph 注入覆盖写回到目标地图 .gil（真源地图）。",
    )
    parser.add_argument(
        "--inject-skip-non-empty-check",
        dest="inject_skip_non_empty_check",
        action="store_true",
        help="注入时跳过非空检查（允许覆盖非空且 name 非 `_GSTS*` 的图，风险高）。",
    )
    parser.add_argument(
        "--inject-create-backup",
        dest="inject_create_backup",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="注入覆盖写回前是否创建备份（默认创建）。",
    )
    parser.add_argument(
        "--bundle",
        dest="bundle_enabled",
        action="store_true",
        help="导出为 bundle（附带管理配置侧文件）。",
    )
    parser.add_argument(
        "--bundle-include-signals",
        dest="bundle_include_signals",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="bundle 模式下是否包含 管理配置/信号（默认包含）。",
    )
    parser.add_argument(
        "--bundle-include-ui-guid-registry",
        dest="bundle_include_ui_guid_registry",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="bundle 模式下是否包含 管理配置/UI控件GUID映射/ui_guid_registry.json（默认包含）。",
    )
    parser.add_argument(
        "--pack",
        dest="pack_graphs_to_single_gia",
        action="store_true",
        help="将多张节点图合并打包为单个 .gia（Root.field_1 为 GraphUnit 列表）。",
    )
    parser.add_argument(
        "--pack-file-name",
        dest="pack_output_gia_file_name",
        default="",
        help="合并打包输出的 .gia 文件名（仅文件名，例如 打包一起.gia；默认 <package_id>_packed_graphs.gia）。",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    import math

    node_pos_scale = float(args.node_pos_scale)
    if (not math.isfinite(node_pos_scale)) or float(node_pos_scale) <= 0.0:
        raise ValueError(f"--node-pos-scale 必须为有限的正数（got: {args.node_pos_scale!r}）")

    project_root = Path(args.project_root).resolve()
    if not project_root.is_dir():
        raise FileNotFoundError(str(project_root))

    graph_code_files = [Path(p).resolve() for p in list(args.graph_code_files or []) if str(p).strip() != ""]
    graph_source_roots = [Path(p).resolve() for p in list(args.graph_source_roots or []) if str(p).strip() != ""]
    for r in list(graph_source_roots):
        if not r.is_dir():
            raise FileNotFoundError(str(r))
    output_user_dir = str(args.output_user_dir or "").strip()
    output_user_dir_path = Path(output_user_dir).resolve() if output_user_dir else None

    base_gil_text = str(args.base_gil_for_signal_defs or "").strip()
    base_gil_path = Path(base_gil_text).resolve() if base_gil_text else None
    if base_gil_path is not None and (not base_gil_path.is_file() or base_gil_path.suffix.lower() != ".gil"):
        raise FileNotFoundError(str(base_gil_path))

    id_ref_text = str(args.id_ref_gil_file or "").strip()
    id_ref_gil_file = Path(id_ref_text).resolve() if id_ref_text else None
    if id_ref_gil_file is not None:
        if not id_ref_gil_file.is_file():
            raise FileNotFoundError(str(id_ref_gil_file))
        if id_ref_gil_file.suffix.lower() != ".gil":
            raise ValueError(f"--id-ref-gil 必须为 .gil 文件：{str(id_ref_gil_file)}")

    overrides_text = str(args.id_ref_overrides_json_file or "").strip()
    id_ref_overrides_json_file = Path(overrides_text).resolve() if overrides_text else None
    if id_ref_overrides_json_file is not None and not id_ref_overrides_json_file.is_file():
        raise FileNotFoundError(str(id_ref_overrides_json_file))

    inject_gil_text = str(args.inject_target_gil_file or "").strip()
    inject_target_gil_file = Path(inject_gil_text).resolve() if inject_gil_text else None
    if inject_target_gil_file is not None and (not inject_target_gil_file.is_file() or inject_target_gil_file.suffix.lower() != ".gil"):
        raise FileNotFoundError(str(inject_target_gil_file))

    report_json_text = str(args.report_json or "").strip()
    report_json_path = Path(report_json_text).resolve() if report_json_text else None

    from ugc_file_tools.pipelines.project_export_gia import ProjectExportGiaPlan, run_project_export_to_gia

    out_dir_name = str(args.output_dir_name_in_out or "").strip()
    if out_dir_name == "":
        out_dir_name = f"{project_root.name}_gia_export"

    plan = ProjectExportGiaPlan(
        project_archive_path=project_root,
        graphs_scope=str(args.graphs_scope),
        graph_scan_all=bool(args.graph_scan_all),
        graph_code_files=graph_code_files if graph_code_files else None,
        graph_source_roots=graph_source_roots if graph_source_roots else None,
        output_dir_name_in_out=str(out_dir_name),
        output_user_dir=output_user_dir_path,
        node_pos_scale=float(node_pos_scale),
        allow_unresolved_ui_keys=bool(args.allow_unresolved_ui_keys),
        ui_export_record_id=(str(args.ui_export_record).strip() or None),
        base_gil_for_signal_defs=base_gil_path,
        id_ref_gil_file=id_ref_gil_file,
        id_ref_overrides_json_file=id_ref_overrides_json_file,
        inject_target_gil_file=inject_target_gil_file,
        inject_skip_non_empty_check=bool(args.inject_skip_non_empty_check),
        inject_create_backup=bool(args.inject_create_backup),
        bundle_enabled=bool(args.bundle_enabled),
        bundle_include_signals=bool(args.bundle_include_signals),
        bundle_include_ui_guid_registry=bool(args.bundle_include_ui_guid_registry),
        pack_graphs_to_single_gia=bool(args.pack_graphs_to_single_gia),
        pack_output_gia_file_name=str(args.pack_output_gia_file_name or "").strip(),
    )

    def _progress_cb(current: int, total: int, label: str) -> None:
        # 供 UI 调用（子进程 stderr 解析）：
        # - `[current/total] label`
        print(f"[{int(current)}/{int(total)}] {str(label or '').strip()}", file=sys.stderr, flush=True)

    report = run_project_export_to_gia(plan=plan, progress_cb=_progress_cb)

    if report_json_path is not None:
        report_json_path.parent.mkdir(parents=True, exist_ok=True)
        report_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 80)
    print("项目存档 → 导出 .gia 完成：")
    for k in sorted(report.keys()):
        print(f"- {k}: {report.get(k)}")
    print("=" * 80)


if __name__ == "__main__":
    main()



