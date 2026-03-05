from __future__ import annotations

"""
validate-graphs CLI 运行器（共享模块）。

目标：
- 统一 “解析参数 → 收集 targets → 编排校验 → 组织输出/JSON 报告 → 返回退出码” 的行为；
- 供 `app.cli.graph_tools validate-graphs` 复用，避免多套实现漂移；
- 本模块只做 CLI 编排与输出组织，不实现任何校验规则。
"""

import argparse
import json
from pathlib import Path
from typing import List

from engine.validate.graph_validation_cli_reporting import (
    build_folder_stats,
    build_issue_summary,
    build_validate_graphs_json_report,
    group_issues_by_file,
    print_file_details,
    print_summary,
)
from engine.validate.graph_validation_orchestrator import (
    ValidateGraphsOrchestrationOptions,
    collect_validate_graphs_engine_issues,
)
from engine.validate.graph_validation_targets import (
    resolve_graph_validation_targets,
)
from engine.validate.issue import EngineIssue

__all__ = [
    "add_validate_graphs_cli_args",
    "run_validate_graphs_cli",
]


def add_validate_graphs_cli_args(parser: argparse.ArgumentParser) -> None:
    """向 parser 添加 validate-graphs 子命令所需的统一参数集合。"""
    parser.add_argument(
        "targets",
        nargs="*",
        help="待校验的文件、通配符或目录；为空或 --all 时校验节点图与复合节点库全量",
    )
    parser.add_argument(
        "-f",
        "--file",
        dest="single_files",
        action="append",
        default=[],
        help="常用单文件校验入口，可重复，例如 -f assets/资源库/项目存档/测试项目/节点图/server/某图.py",
    )
    parser.add_argument(
        "--all",
        dest="validate_all",
        action="store_true",
        help="校验 assets/资源库/项目存档/<package_id>/节点图 与 复合节点库 全量",
    )
    parser.add_argument(
        "--strict",
        "--strict-entity-wire-only",
        dest="strict_entity_wire_only",
        action="store_true",
        help="实体入参严格模式，仅允许连线/事件参数",
    )
    parser.add_argument(
        "--no-cache",
        dest="disable_cache",
        action="store_true",
        help="禁用校验缓存（默认启用）",
    )
    parser.add_argument(
        "--no-composite-struct-check",
        dest="disable_composite_struct_check",
        action="store_true",
        help="禁用复合节点结构校验（默认启用；用于对齐 UI 的“缺少数据来源/未连接”等检查）",
    )
    parser.add_argument(
        "--json",
        dest="output_json",
        action="store_true",
        help="以 JSON 输出完整报告（仅输出 JSON；适合脚本/CI 消费）",
    )
    parser.add_argument(
        "--fix",
        dest="apply_fixes",
        action="store_true",
        help=(
            "对部分可自动修复的问题执行 QuickFix（会修改文件）。\n"
            "- 当前支持：补齐未声明的节点图变量（GRAPH_VARIABLES）。\n"
            "- 建议先用 --fix-dry-run 预览改动。"
        ),
    )
    parser.add_argument(
        "--fix-dry-run",
        dest="fix_dry_run",
        action="store_true",
        help="预览 QuickFix 计划（不写盘，不修改文件）。",
    )


def _resolve_targets_or_print_errors(
    parsed_args: argparse.Namespace,
    workspace_root: Path,
    *,
    empty_match_description: str | None,
) -> List[Path] | None:
    resolution = resolve_graph_validation_targets(
        workspace_root=workspace_root,
        targets=list(getattr(parsed_args, "targets", [])),
        single_files=list(getattr(parsed_args, "single_files", [])),
        validate_all=bool(getattr(parsed_args, "validate_all", False)),
        empty_match_description=str(empty_match_description) if empty_match_description else "assets/资源库/{节点图,复合节点库}/**/*.py",
    )
    if resolution.errors:
        for message in resolution.errors:
            print(message)
        return None
    return list(resolution.targets)


def run_validate_graphs_cli(
    parsed_args: argparse.Namespace,
    workspace_root: Path,
    *,
    json_schema: str,
    json_schema_version: int = 1,
    empty_match_description: str | None = None,
    include_line_span: bool = True,
    include_location: bool = True,
    include_port: bool = True,
    annotate_legacy_packages_bucket: bool = True,
    print_workspace_root_in_text_mode: bool = False,
) -> int:
    """运行 validate-graphs 并返回退出码（0=通过，1=失败）。"""
    targets = _resolve_targets_or_print_errors(
        parsed_args,
        workspace_root,
        empty_match_description=empty_match_description,
    )
    if targets is None:
        return 1

    mode_desc = "STRICT" if bool(getattr(parsed_args, "strict_entity_wire_only", False)) else "DEFAULT"

    output_json = bool(getattr(parsed_args, "output_json", False))
    apply_fixes = bool(getattr(parsed_args, "apply_fixes", False))
    fix_dry_run = bool(getattr(parsed_args, "fix_dry_run", False))
    if apply_fixes and fix_dry_run:
        print("[ERROR] --fix 与 --fix-dry-run 不能同时使用。")
        return 1
    if (apply_fixes or fix_dry_run) and output_json:
        print("[ERROR] --fix/--fix-dry-run 与 --json 不兼容（避免 stdout 混入非 JSON 文本）。")
        return 1

    if not output_json:
        print("=" * 80)
        print(f"开始验证 {len(targets)} 个文件（模式: {mode_desc}）...")
        if print_workspace_root_in_text_mode:
            print(f"workspace_root: {workspace_root}")
        print("=" * 80)
        print()

    if apply_fixes or fix_dry_run:
        from engine.validate.graph_validation_quickfixes import apply_graph_validation_quickfixes

        dry_run = bool(fix_dry_run) or (not bool(apply_fixes))
        if not output_json:
            mode_text = "DRY-RUN" if dry_run else "APPLY"
            print("=" * 80)
            print(f"[FIX] QuickFix 开始（{mode_text}）: 扫描并尝试自动修复可补齐的问题...")
            print("=" * 80)
        fix_actions = apply_graph_validation_quickfixes(targets, workspace_root, dry_run=dry_run)
        if not output_json:
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
        strict_entity_wire_only=bool(getattr(parsed_args, "strict_entity_wire_only", False)),
        use_cache=bool(not getattr(parsed_args, "disable_cache", False)),
        enable_composite_struct_check=bool(not getattr(parsed_args, "disable_composite_struct_check", False)),
    )
    all_issues: List[EngineIssue] = collect_validate_graphs_engine_issues(
        targets,
        workspace_root,
        options=orchestration_options,
    )

    issues_by_file = group_issues_by_file(all_issues, workspace_root)
    folder_stats = build_folder_stats(targets, issues_by_file, workspace_root)
    level_counts, category_counts, code_counts = build_issue_summary(all_issues)
    error_count = int(level_counts.get("error", 0) or 0)

    if output_json:
        payload = build_validate_graphs_json_report(
            schema=str(json_schema),
            schema_version=int(json_schema_version),
            targets=targets,
            issues=all_issues,
            issues_by_file=issues_by_file,
            workspace_root=workspace_root,
            mode_desc=mode_desc,
            strict_entity_wire_only=bool(getattr(parsed_args, "strict_entity_wire_only", False)),
            disable_cache=bool(getattr(parsed_args, "disable_cache", False)),
            disable_composite_struct_check=bool(getattr(parsed_args, "disable_composite_struct_check", False)),
            folder_stats=folder_stats,
            level_counts=level_counts,
            category_counts=category_counts,
            code_counts=code_counts,
        )
        # CI/PowerShell 管道下曾出现编码链路导致 JSON 损坏（非 ASCII 字符被破坏甚至破坏引号闭合）。
        # `--json` 主要用于脚本/CI 消费：优先保证“跨编码环境稳定可解析”，因此强制 ensure_ascii=True。
        print(json.dumps(payload, ensure_ascii=True, indent=2))
        return 1 if error_count > 0 else 0

    failed_files = print_file_details(
        targets,
        issues_by_file,
        workspace_root,
        include_line_span=bool(include_line_span),
        include_location=bool(include_location),
        include_port=bool(include_port),
    )
    print_summary(
        len(targets),
        failed_files,
        folder_stats,
        level_counts,
        category_counts,
        code_counts,
        annotate_legacy_packages_bucket=bool(annotate_legacy_packages_bucket),
    )
    if error_count > 0:
        return 1
    if all_issues:
        print("\n[SUCCESS] 无错误（存在 warning/info；不会阻断退出码）")
    else:
        print("\n[SUCCESS] 所有文件通过（无问题）")
    return 0


