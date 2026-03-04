from __future__ import annotations

import argparse
from pathlib import Path

from engine.validate.graph_validation_cli_runner import (
    add_validate_graphs_cli_args,
    run_validate_graphs_cli,
)


def register_graph_validation_commands(subparsers: argparse._SubParsersAction) -> None:
    validate_graphs_parser = subparsers.add_parser(
        "validate-graphs",
        help="校验节点图/复合节点（产品内置校验入口；release 中为 Ayaya_Miliastra_Editor_Tools.exe validate-graphs）",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    add_validate_graphs_cli_args(validate_graphs_parser)
    validate_graphs_parser.set_defaults(_runner=run_validate_graphs)

    validate_file_parser = subparsers.add_parser(
        "validate-file",
        help="校验单个节点图文件（输出与节点图脚本自检类似的通过/错误/警告列表）",
    )
    validate_file_parser.add_argument(
        "file",
        help="节点图文件路径（可相对 workspace_root）",
    )
    validate_file_parser.add_argument(
        "--strict",
        dest="strict",
        action="store_true",
        help=(
            "严格模式（fail-closed）：先用 GraphCodeParser(strict=True) 解析该文件，"
            "以对齐资源加载/批量导出链路；若 strict 下拒绝解析则直接抛错退出。"
        ),
    )
    validate_file_parser.add_argument(
        "--fix",
        dest="apply_fixes",
        action="store_true",
        help="对单文件执行 QuickFix（会修改文件；建议先用 --fix-dry-run 预览）。",
    )
    validate_file_parser.add_argument(
        "--fix-dry-run",
        dest="fix_dry_run",
        action="store_true",
        help="预览 QuickFix 计划（不写盘，不修改文件）。",
    )
    validate_file_parser.set_defaults(_runner=run_validate_file)


def run_validate_graphs(parsed_args: argparse.Namespace, workspace_root: Path) -> int:
    return run_validate_graphs_cli(
        parsed_args,
        workspace_root,
        json_schema="app.cli.graph_tools.validate_graphs.report",
        json_schema_version=1,
        empty_match_description=None,
        include_line_span=False,
        include_location=True,
        include_port=False,
        annotate_legacy_packages_bucket=True,
        print_workspace_root_in_text_mode=True,
    )


def run_validate_file(parsed_args: argparse.Namespace, workspace_root: Path) -> int:
    from engine.validate import validate_file as validate_node_graph_file
    from engine.validate.node_graph_validator import format_validate_file_report
    from engine.validate.node_graph_validator import strict_parse_file

    raw_path = Path(parsed_args.file)
    target_path = raw_path if raw_path.is_absolute() else (workspace_root / raw_path)
    target_path = target_path.resolve()

    apply_fixes = bool(getattr(parsed_args, "apply_fixes", False))
    fix_dry_run = bool(getattr(parsed_args, "fix_dry_run", False))
    if apply_fixes and fix_dry_run:
        print("[ERROR] --fix 与 --fix-dry-run 不能同时使用。")
        return 1
    if apply_fixes or fix_dry_run:
        from engine.validate.graph_validation_quickfixes import apply_graph_validation_quickfixes

        dry_run = bool(fix_dry_run) or (not bool(apply_fixes))
        mode_text = "DRY-RUN" if dry_run else "APPLY"
        print("=" * 80)
        print(f"[FIX] QuickFix 开始（{mode_text}）: {target_path}")
        print("=" * 80)
        actions = apply_graph_validation_quickfixes([target_path], workspace_root, dry_run=dry_run)
        if not actions:
            print("[FIX] 未发现可自动修复项。\n")
        else:
            for action in actions:
                print(f"  - {action.file_path}: {action.summary}")
            if dry_run:
                print("\n[FIX] DRY-RUN：未写盘。若确认无误，请改用 --fix 执行写入。")
            print()

    if bool(getattr(parsed_args, "strict", False)):
        # strict fail-closed：对齐资源加载/批量导出链路。
        # 注意：strict 失败会抛异常（不吞异常），由 CLI 直接以非 0 退出并输出 traceback。
        strict_parse_file(target_path)

    passed, errors, warnings = validate_node_graph_file(target_path)
    print(
        format_validate_file_report(
            file_path=target_path,
            passed=passed,
            errors=errors,
            warnings=warnings,
        )
    )

    return 0 if passed else 1

