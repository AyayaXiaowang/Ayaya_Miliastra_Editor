from __future__ import annotations

import argparse
from pathlib import Path


def register_validate_all_command(subparsers: argparse._SubParsersAction) -> None:
    validate_all_parser = subparsers.add_parser(
        "validate-all",
        help="全量校验：项目存档(validate-project) + UI源码变量(validate-ui) + 节点图/复合节点(validate-graphs --all)",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    validate_all_parser.add_argument(
        "--package-id",
        default="",
        help="仅校验指定 package_id（不传则校验全部项目存档 + 全量节点图/复合节点）。",
    )
    validate_all_parser.add_argument(
        "--fix",
        dest="apply_fixes",
        action="store_true",
        help=(
            "对全量校验启用 QuickFix（会修改文件；建议先用 --fix-dry-run 预览）。\n"
            "- validate-project：结构体定义目录即分类对齐等\n"
            "- validate-ui：根据 UI 引用自动补齐变量文件与玩家模板引用\n"
            "- validate-graphs：补齐可自动修复的缺失项（例如 GRAPH_VARIABLES 变量声明）"
        ),
    )
    validate_all_parser.add_argument(
        "--fix-dry-run",
        dest="fix_dry_run",
        action="store_true",
        help="预览 QuickFix 计划（不写盘，不修改文件）。",
    )
    validate_all_parser.add_argument(
        "--fail-on-warning",
        dest="fail_on_warning",
        action="store_true",
        help="严格模式：只要存在 warning/info 也视为失败（默认仅 error 视为失败）。",
    )
    validate_all_parser.set_defaults(_runner=run_validate_all)


def run_validate_all(parsed_args: argparse.Namespace, workspace_root: Path) -> int:
    package_id_filter = str(getattr(parsed_args, "package_id", "") or "").strip()
    apply_fixes = bool(getattr(parsed_args, "apply_fixes", False))
    fix_dry_run = bool(getattr(parsed_args, "fix_dry_run", False))
    fail_on_warning = bool(getattr(parsed_args, "fail_on_warning", False))
    if apply_fixes and fix_dry_run:
        print("[ERROR] --fix 与 --fix-dry-run 不能同时使用。")
        return 1

    print("=" * 80)
    print("validate-all：开始全量校验（validate-project / validate-ui / validate-graphs --all）")
    if package_id_filter:
        print(f"- package_id: {package_id_filter}")
    if apply_fixes or fix_dry_run:
        mode_text = "APPLY" if apply_fixes else "DRY-RUN"
        print(f"- quickfix: {mode_text}")
    if fail_on_warning:
        print("- fail_on_warning: True")
    print("=" * 80)
    print()

    # 1) 项目存档级：资源/挂载关系层
    from app.cli.commands.project_tools import run_validate_project

    ns_project = argparse.Namespace(
        package_id=package_id_filter,
        apply_fixes=apply_fixes,
        fix_dry_run=fix_dry_run,
    )
    code_project = run_validate_project(ns_project, workspace_root)

    # 2) UI 源码：变量占位符/来源闭包
    from app.cli.commands.ui_tools import run_validate_ui

    ns_ui = argparse.Namespace(
        package_id=package_id_filter,
        apply_fixes=apply_fixes,
        fix_dry_run=fix_dry_run,
    )
    code_ui = run_validate_ui(ns_ui, workspace_root)

    # 3) 节点图/复合节点：全量扫描（共享 + 全部项目存档）
    # - 不传 package_id：走 --all 全量扫描（覆盖共享 + 全部项目存档）。
    # - 指定 package_id：仅扫描共享 + 当前项目存档目录，避免误把其他包的历史/示例图混入一次校验。
    graphs_args: list[str] = ["validate-graphs"]
    if package_id_filter:
        graphs_args.extend(
            [
                "assets/资源库/共享/节点图",
                "assets/资源库/共享/复合节点库",
                f"assets/资源库/项目存档/{package_id_filter}/节点图",
                f"assets/资源库/项目存档/{package_id_filter}/复合节点库",
            ]
        )
    else:
        graphs_args.append("--all")
    if apply_fixes:
        graphs_args.append("--fix")
    if fix_dry_run:
        graphs_args.append("--fix-dry-run")
    # validate-graphs：默认仅 error 视为失败（warning/info 仍会完整输出，便于程序员发现问题但不阻断流水线）。
    # 如需“0 warning 才通过”，使用 validate-all --fail-on-warning。
    from engine.validate.graph_validation_cli_reporting import (
        build_folder_stats,
        build_issue_summary,
        group_issues_by_file,
        print_file_details,
        print_summary,
    )
    from engine.validate.graph_validation_orchestrator import (
        ValidateGraphsOrchestrationOptions,
        collect_validate_graphs_engine_issues,
    )
    from engine.validate.graph_validation_targets import resolve_graph_validation_targets

    graphs_resolution = resolve_graph_validation_targets(
        workspace_root=workspace_root,
        targets=[str(x) for x in graphs_args[1:] if str(x) and not str(x).startswith("--")],
        single_files=[],
        validate_all=("--all" in graphs_args),
        empty_match_description="assets/资源库/{节点图,复合节点库}/**/*.py",
    )
    if graphs_resolution.errors:
        for message in graphs_resolution.errors:
            print(message)
        code_graphs = 1
    else:
        targets = list(graphs_resolution.targets)
        mode_desc = "DEFAULT"

        print("=" * 80)
        print(f"开始验证 {len(targets)} 个文件（模式: {mode_desc}）...")
        print(f"workspace_root: {workspace_root}")
        print("=" * 80)
        print()

        if apply_fixes or fix_dry_run:
            from engine.validate.graph_validation_quickfixes import apply_graph_validation_quickfixes

            dry_run = bool(fix_dry_run) or (not bool(apply_fixes))
            mode_text = "DRY-RUN" if dry_run else "APPLY"
            print("=" * 80)
            print(f"[FIX] QuickFix 开始（{mode_text}）: 扫描并尝试自动修复可补齐的问题...")
            print("=" * 80)
            fix_actions = apply_graph_validation_quickfixes(targets, workspace_root, dry_run=dry_run)
            if not fix_actions:
                print("[FIX] 未发现可自动修复项。\n")
            else:
                print(f"[FIX] 已处理 {len(fix_actions)} 项：")
                for action in fix_actions:
                    print(f"  - {action.file_path}: {action.summary}")
                if dry_run:
                    print("\n[FIX] DRY-RUN：未写盘。若确认无误，请改用 --fix 执行写入。")
                print()

        orchestration_options = ValidateGraphsOrchestrationOptions(
            strict_entity_wire_only=False,
            use_cache=True,
            enable_composite_struct_check=True,
        )
        all_issues = collect_validate_graphs_engine_issues(
            targets,
            workspace_root,
            options=orchestration_options,
        )
        issues_by_file = group_issues_by_file(all_issues, workspace_root)
        folder_stats = build_folder_stats(targets, issues_by_file, workspace_root)
        level_counts, category_counts, code_counts = build_issue_summary(all_issues)

        failed_files = print_file_details(
            targets,
            issues_by_file,
            workspace_root,
            include_line_span=False,
            include_location=True,
            include_port=False,
        )
        print_summary(
            len(targets),
            failed_files,
            folder_stats,
            level_counts,
            category_counts,
            code_counts,
            annotate_legacy_packages_bucket=True,
        )

        error_count = int(level_counts.get("error", 0) or 0)
        if error_count > 0:
            code_graphs = 1
        elif fail_on_warning and all_issues:
            code_graphs = 1
        else:
            if all_issues:
                print("\n[OK] validate-all：节点图/复合节点仅存在 warning/info，按非致命处理（可用 --fail-on-warning 改为严格模式）。")
            code_graphs = 0

    # 汇总：不短路，确保一次输出覆盖全部校验结果。
    failed = [
        (name, code)
        for name, code in [
            ("validate-project", code_project),
            ("validate-ui", code_ui),
            ("validate-graphs", code_graphs),
        ]
        if code != 0
    ]
    print("=" * 70)
    print("validate-all：综合结果")
    print("=" * 70)
    print(f"- validate-project: {code_project}")
    print(f"- validate-ui:      {code_ui}")
    print(f"- validate-graphs:  {code_graphs}")
    if not failed:
        print("\n✅ validate-all 通过：未发现错误。")
        return 0
    print(f"\n❌ validate-all 失败：{len(failed)} 个子校验返回非 0。")
    for name, code in failed:
        print(f"  - {name}: {code}")
    return 1

