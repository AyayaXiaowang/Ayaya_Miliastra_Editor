from __future__ import annotations

import argparse
from pathlib import Path


def register_custom_var_tools_commands(subparsers: argparse._SubParsersAction) -> None:
    audit_custom_vars_parser = subparsers.add_parser(
        "audit-custom-vars",
        help="审计节点图中对实体自定义变量的读写引用点（where-used 报告）",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    audit_custom_vars_parser.add_argument(
        "--package-id",
        default="",
        help="仅审计指定 package_id（不传则审计全部项目存档）。",
    )
    audit_custom_vars_parser.add_argument(
        "--out-dir",
        default="",
        help="输出目录（可相对 workspace_root）。默认写入 app/runtime/cache/variable_audit/<package_id>/",
    )
    audit_custom_vars_parser.add_argument(
        "--name-prefix",
        default="",
        help="输出文件名前缀（可用于区分多次导出）。",
    )
    audit_custom_vars_parser.set_defaults(_runner=run_audit_custom_vars)

    sync_custom_vars_parser = subparsers.add_parser(
        "sync-custom-vars",
        help="同步自定义变量注册表（refs-only）：一处声明→同步引用点（玩家模板/关卡实体/第三方存放实体）",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    sync_custom_vars_parser.add_argument(
        "--package-id",
        required=True,
        help=(
            "项目存档 package_id（读取：assets/资源库/项目存档/<package_id>/管理配置/关卡变量/自定义变量注册表.py；"
            "自动更新引用点（玩家模板/关卡实体/第三方存放实体）与必要的存放资源）。"
        ),
    )
    sync_custom_vars_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览同步动作（不写盘，不修改文件）。",
    )
    sync_custom_vars_parser.set_defaults(_runner=run_sync_custom_vars)


def run_audit_custom_vars(parsed_args: argparse.Namespace, workspace_root: Path) -> int:
    from engine.resources import build_resource_index_context

    from app.cli.custom_variable_usage_auditor import (
        CustomVariableAuditReport,
        collect_graph_py_files,
        collect_ui_placeholder_var_contract_from_ui_source_dir,
        scan_custom_variable_usages,
        write_report,
    )

    _resource_manager, package_index_manager = build_resource_index_context(workspace_root)

    package_id_filter = str(getattr(parsed_args, "package_id", "") or "").strip()
    out_dir_arg = str(getattr(parsed_args, "out_dir", "") or "").strip()
    name_prefix = str(getattr(parsed_args, "name_prefix", "") or "").strip()

    package_infos = package_index_manager.list_packages()
    if not package_infos:
        print("未找到任何项目存档目录（assets/资源库/项目存档/*），跳过审计。")
        return 0

    selected: list[str] = []
    for info in package_infos:
        if not isinstance(info, dict):
            continue
        package_id = str(info.get("package_id") or "").strip()
        if not package_id:
            continue
        if package_id_filter and package_id_filter != package_id:
            continue
        selected.append(package_id)

    if not selected:
        if package_id_filter:
            raise ValueError(
                f"未找到指定项目存档：{package_id_filter}（请确认 assets/资源库/项目存档/<package_id> 目录存在）。"
            )
        print("未找到可审计的项目存档，跳过。")
        return 0

    print("=" * 80)
    print("audit-custom-vars：开始")
    if package_id_filter:
        print(f"- package_id: {package_id_filter}")
    print("=" * 80)
    print()

    for package_id in selected:
        shared_graph_root = (workspace_root / "assets" / "资源库" / "共享" / "节点图").resolve()
        package_graph_root = (workspace_root / "assets" / "资源库" / "项目存档" / package_id / "节点图").resolve()
        graph_roots: list[Path] = [shared_graph_root, package_graph_root]
        graph_roots = [p for p in graph_roots if p.is_dir()]

        py_files = collect_graph_py_files(graph_roots)
        usages = scan_custom_variable_usages(py_files)
        ui_contract = collect_ui_placeholder_var_contract_from_ui_source_dir(
            (workspace_root / "assets" / "资源库" / "项目存档" / package_id / "管理配置" / "UI源码").resolve()
        )
        report = CustomVariableAuditReport(
            graph_roots=[p.as_posix() for p in graph_roots],
            scanned_files=len(py_files),
            usages=usages,
            ui_contract=ui_contract,
        )

        if out_dir_arg:
            out_dir = Path(out_dir_arg)
            if not out_dir.is_absolute():
                out_dir = workspace_root / out_dir
            out_dir = out_dir.resolve()
        else:
            out_dir = (workspace_root / "app" / "runtime" / "cache" / "variable_audit" / package_id).resolve()

        json_path, md_path = write_report(report, out_dir, name_prefix=name_prefix)
        summary = report.serialize().get("summary") or {}

        print("-" * 80)
        print(f"package_id: {package_id}")
        print(f"graph_roots: {', '.join(report.graph_roots) if report.graph_roots else '<empty>'}")
        print(f"scanned_files: {len(py_files)}")
        print(f"total_usages: {summary.get('total_usages')}")
        print(f"literal_usages: {summary.get('literal_usages')}")
        print(f"dynamic_usages: {summary.get('dynamic_usages')}")
        print(f"unique_literal_var_names: {summary.get('unique_literal_var_names')}")
        print()
        print(f"- json: {json_path}")
        print(f"- md:   {md_path}")
        print()

    print("=" * 80)
    print("audit-custom-vars：完成")
    print("=" * 80)
    return 0


def run_sync_custom_vars(parsed_args: argparse.Namespace, workspace_root: Path) -> int:
    from app.cli.auto_custom_variable_sync import sync_auto_custom_variables_from_registry

    package_id = str(getattr(parsed_args, "package_id", "") or "").strip()
    dry_run = bool(getattr(parsed_args, "dry_run", False))

    actions = sync_auto_custom_variables_from_registry(
        workspace_root=workspace_root,
        package_id=package_id,
        dry_run=dry_run,
    )

    print("=" * 80)
    print("sync-custom-vars：完成")
    print("=" * 80)
    for action in actions:
        print(f"- {action.file_path}: {action.summary}")
    print()
    return 0

