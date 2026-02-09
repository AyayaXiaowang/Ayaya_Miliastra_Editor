from __future__ import annotations

"""
Ayaya_Miliastra_Editor 便携版工具入口（CLI）。

目标：
- 源码环境：支持 `python -X utf8 -m app.cli.graph_tools ...`
- PyInstaller 冻结环境：支持 `Ayaya_Miliastra_Editor_Tools.exe ...`（无需用户安装 Python）

约定：
- 冻结运行时默认以 exe 所在目录作为 workspace_root，并在启动阶段 chdir 到该目录；
  因此发布产物要求 `assets/` 与 exe 同级外置（用户可编辑）。
- 本工具只做静态校验/检查，不执行任何节点业务逻辑（与引擎校验边界一致）。
"""

import argparse
import os
import sys
import shutil
from datetime import datetime
from pathlib import Path
from typing import Sequence


if not __package__ and not getattr(sys, "frozen", False):
    raise SystemExit(
        "请从项目根目录使用模块方式运行：\n"
        "  python -X utf8 -m app.cli.graph_tools --help\n"
        "（不再支持通过脚本内 sys.path.insert 的方式运行）"
    )

# workspace_root 推导与 settings 初始化唯一真源
from engine.utils.workspace import resolve_workspace_root, init_settings_for_workspace

# 仅在“模块运行 / 冻结运行”模式下导入引擎依赖，避免用户误用 `python app/cli/graph_tools.py`
# 时因 sys.path 未注入而出现误导性 ImportError。
from engine.utils.logging.console_encoding import (  # noqa: E402
    install_utf8_streams_on_windows as _install_utf8_streams_on_windows_impl,
)
from engine.validate.graph_validation_cli_runner import (  # noqa: E402
    add_validate_graphs_cli_args,
    run_validate_graphs_cli,
)


def _install_utf8_streams_on_windows() -> None:
    _install_utf8_streams_on_windows_impl(errors="replace")


def _parse_cli(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="graph_tools",
        description="Ayaya_Miliastra_Editor 工具入口（校验/诊断）",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--root",
        dest="workspace_root",
        default="",
        help="工作区根目录（默认：源码=仓库根目录；冻结=exe 所在目录）",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_graphs_parser = subparsers.add_parser(
        "validate-graphs",
        help="校验节点图/复合节点（产品内置校验入口；release 中为 Ayaya_Miliastra_Editor_Tools.exe validate-graphs）",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    add_validate_graphs_cli_args(validate_graphs_parser)

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

    validate_package_parser = subparsers.add_parser(
        "validate-project",
        help="校验项目存档（目录模式；资源/挂载关系层；等价于 UI「验证」的项目存档部分）",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    validate_package_parser.add_argument(
        "--package-id",
        default="",
        help="仅校验指定 package_id（不传则校验全部项目存档）",
    )
    validate_package_parser.add_argument(
        "--fix",
        dest="apply_fixes",
        action="store_true",
        help="对项目存档执行 QuickFix（会修改文件；建议先用 --fix-dry-run 预览）。",
    )
    validate_package_parser.add_argument(
        "--fix-dry-run",
        dest="fix_dry_run",
        action="store_true",
        help="预览 QuickFix 计划（不写盘，不修改文件）。",
    )

    # 兼容旧命令名：validate-package（目录即项目存档模式下仍然有效，但不再对外推荐）
    validate_package_legacy_parser = subparsers.add_parser(
        "validate-package",
        help="兼容旧命令名（建议改用 validate-project）",
    )
    validate_package_legacy_parser.add_argument(
        "--package-id",
        default="",
        help="仅校验指定 package_id（不传则校验全部项目存档）",
    )
    validate_package_legacy_parser.add_argument(
        "--fix",
        dest="apply_fixes",
        action="store_true",
        help="对项目存档执行 QuickFix（会修改文件；建议先用 --fix-dry-run 预览）。",
    )
    validate_package_legacy_parser.add_argument(
        "--fix-dry-run",
        dest="fix_dry_run",
        action="store_true",
        help="预览 QuickFix 计划（不写盘，不修改文件）。",
    )

    setup_doc_links_parser = subparsers.add_parser(
        "setup-doc-links",
        help="为项目存档补齐共享文档 Junction（零复制共享）",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    setup_doc_links_parser.add_argument(
        "--package-id",
        default="",
        help="仅处理指定 package_id（不传则处理全部项目存档）",
    )

    subparsers.add_parser(
        "print-workspace",
        help="打印当前解析到的 workspace_root 与 assets 路径（用于排查路径问题）",
    )

    cleanup_dumps_parser = subparsers.add_parser(
        "cleanup-external-dumps",
        help="清理资源库下的外部解析产物目录（例如 assets/资源库/存档包）",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    cleanup_dumps_parser.add_argument(
        "--action",
        choices=["move", "delete"],
        default="move",
        help="清理动作：move=移动到 --dest 目录；delete=直接删除（不可恢复）。默认 move。",
    )
    cleanup_dumps_parser.add_argument(
        "--dest",
        default="tmp/external_dumps",
        help="当 action=move 时的目标根目录（相对 workspace_root 或绝对路径）。默认 tmp/external_dumps",
    )
    cleanup_dumps_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览动作（不写盘、不移动、不删除）。",
    )

    validate_ui_parser = subparsers.add_parser(
        "validate-ui",
        help="校验管理配置 UI 源码中的变量占位符（支持 {{ps.}}/{{p1.}}/{{lv.}} 与 {1:ps.}）",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    validate_ui_parser.add_argument(
        "--package-id",
        default="",
        help="仅校验指定 package_id（不传则校验全部项目存档）",
    )
    validate_ui_parser.add_argument(
        "--fix",
        dest="apply_fixes",
        action="store_true",
        help="自动补齐 UI 引用的变量定义（会写入变量文件并更新玩家模板 custom_variable_file）。",
    )
    validate_ui_parser.add_argument(
        "--fix-dry-run",
        dest="fix_dry_run",
        action="store_true",
        help="预览自动补齐计划（不写盘，不修改文件）。",
    )

    extract_ui_defaults_parser = subparsers.add_parser(
        "extract-ui-defaults",
        help="从 UI HTML 的 data-ui-variable-defaults 抽取并导出拆分后的 JSON（用于一键同步 UI 字典默认值）",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    extract_ui_defaults_parser.add_argument(
        "--package-id",
        default="",
        help=(
            "项目存档 package_id（用于推导默认 HTML 路径与默认输出目录）。\n"
            "默认输出：app/runtime/cache/ui_artifacts/<package_id>/ui_defaults/"
        ),
    )
    extract_ui_defaults_parser.add_argument(
        "--html",
        default="",
        help=(
            "目标 HTML 路径（可相对 workspace_root）。\n"
            "若未传且传了 --package-id，则默认使用：assets/资源库/项目存档/<package_id>/管理配置/UI源码/ceshi_rect.html"
        ),
    )
    extract_ui_defaults_parser.add_argument(
        "--out-dir",
        default="",
        help=(
            "输出目录（可相对 workspace_root）。默认写入运行时缓存 ui_artifacts 目录，避免污染资源库。"
        ),
    )
    extract_ui_defaults_parser.add_argument(
        "--name-prefix",
        default="",
        help="输出文件名前缀（可用于区分多次导出）。",
    )

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

    apply_ui_defaults_parser = subparsers.add_parser(
        "apply-ui-defaults",
        help="将 UI HTML 的 data-ui-variable-defaults 一键写入关卡变量默认值（写到 UI_关卡变量_自动生成.py）",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    apply_ui_defaults_parser.add_argument(
        "--package-id",
        required=True,
        help="项目存档 package_id（目标写入：assets/资源库/项目存档/<package_id>/管理配置/关卡变量/自定义变量/UI_关卡变量_自动生成.py）",
    )
    apply_ui_defaults_parser.add_argument(
        "--all",
        action="store_true",
        help="扫描项目存档 UI源码 目录下的所有 HTML（仅处理包含 data-ui-variable-defaults 的页面），并合并写入。",
    )
    apply_ui_defaults_parser.add_argument(
        "--html",
        default="",
        help=(
            "目标 HTML 路径（可相对 workspace_root）。\n"
            "默认：assets/资源库/项目存档/<package_id>/管理配置/UI源码/ceshi_rect.html"
        ),
    )
    apply_ui_defaults_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览写入动作（不写盘）。",
    )
    apply_ui_defaults_parser.add_argument(
        "--prune-managed-keys",
        action="store_true",
        help=(
            "可选：删除“曾由 data-ui-variable-defaults 管理过”的键，且本轮所有页面都不再声明该键。\n"
            "默认关闭：只增/改不删，避免误删无关内容。"
        ),
    )

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

    return parser.parse_args(list(argv))


def _run_validate_graphs(parsed_args: argparse.Namespace, workspace_root: Path) -> int:
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


def _run_validate_file(parsed_args: argparse.Namespace, workspace_root: Path) -> int:
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


def _run_validate_package(parsed_args: argparse.Namespace, workspace_root: Path) -> int:
    """项目存档级综合校验（资源/挂载关系层）。"""
    from engine.validate import ComprehensiveValidator
    from engine.resources import PackageView, build_resource_index_context

    # ANSI 颜色码（仅用于控制台输出，不影响退出码）
    class Colors:
        RED = "\u001b[31m"
        YELLOW = "\u001b[33m"
        GREEN = "\u001b[32m"
        BLUE = "\u001b[34m"
        CYAN = "\u001b[36m"
        RESET = "\u001b[0m"
        BOLD = "\u001b[1m"

    def print_colored(text: str, color: str = Colors.RESET) -> None:
        print(f"{color}{text}{Colors.RESET}")

    package_id_filter = str(getattr(parsed_args, "package_id", "") or "").strip()
    apply_fixes = bool(getattr(parsed_args, "apply_fixes", False))
    fix_dry_run = bool(getattr(parsed_args, "fix_dry_run", False))
    if apply_fixes and fix_dry_run:
        print_colored("[ERROR] --fix 与 --fix-dry-run 不能同时使用。", Colors.RED)
        return 1

    resource_manager, package_index_manager = build_resource_index_context(workspace_root)

    package_infos = package_index_manager.list_packages()
    if not package_infos:
        print_colored("未找到任何项目存档目录（assets/资源库/项目存档/*），跳过项目存档校验。", Colors.YELLOW)
        return 0

    selected_infos: list[dict] = []
    for info in package_infos:
        if not isinstance(info, dict):
            continue
        package_id = str(info.get("package_id") or "").strip()
        if not package_id:
            continue
        if package_id_filter and package_id_filter != package_id:
            continue
        selected_infos.append(info)

    if not selected_infos:
        if package_id_filter:
            print_colored(
                f"未找到指定项目存档：{package_id_filter}（请确认 assets/资源库/项目存档/<package_id> 目录存在）。",
                Colors.YELLOW,
            )
            return 1
        print_colored("未找到可校验的项目存档目录，跳过项目存档校验。", Colors.YELLOW)
        return 0

    print_colored(f"发现 {len(selected_infos)} 个项目存档，开始逐个校验...", Colors.BLUE)

    # ===== QuickFix（可选）=====
    if apply_fixes or fix_dry_run:
        from engine.validate.struct_definition_quickfixes import apply_struct_definition_quickfixes

        dry_run = bool(fix_dry_run) or (not bool(apply_fixes))
        mode_text = "DRY-RUN" if dry_run else "APPLY"

        all_fix_actions: list = []
        for info in selected_infos:
            package_id = str(info.get("package_id") or "").strip()
            if not package_id:
                continue
            all_fix_actions.extend(
                apply_struct_definition_quickfixes(
                    workspace_root=workspace_root,
                    package_id=package_id,
                    dry_run=dry_run,
                )
            )

        print("=" * 80)
        print(f"[FIX] QuickFix 开始（{mode_text}）: validate-project")
        print("=" * 80)
        if not all_fix_actions:
            print("[FIX] 未发现可自动修复项。\n")
        else:
            for action in all_fix_actions:
                print(f"  - {action.file_path}: {action.summary}")
            if dry_run:
                print("\n[FIX] DRY-RUN：未写盘。若确认无误，请改用 --fix 执行写入。")
            print()

    allowed_categories = {
        "关卡实体",
        "模板",
        "实体摆放",
        "管理配置",
        "节点图挂载",
        "信号系统",
        "结构体系统",
        "资源系统",
    }

    total_errors = 0
    total_warnings = 0

    for info in selected_infos:
        package_id = str(info.get("package_id") or "").strip()
        if not package_id:
            continue

        # 关键：资源索引必须切到“共享 + 当前项目存档”作用域，否则可能串包。
        resource_manager.rebuild_index(active_package_id=package_id)
        # 关键：PackageIndex 派生依赖当前 ResourceManager 作用域；切换后必须失效缓存。
        package_index_manager.invalidate_package_index_cache(package_id)
        package_index = package_index_manager.load_package_index(package_id)
        if package_index is None:
            continue

        package_view = PackageView(package_index, resource_manager)
        validator = ComprehensiveValidator(package_view, resource_manager, verbose=False)
        issues = validator.validate_all()

        display_issues = [issue for issue in issues if issue.category in allowed_categories]

        error_count = sum(1 for issue in display_issues if issue.level == "error")
        warning_count = sum(1 for issue in display_issues if issue.level == "warning")
        info_count = sum(1 for issue in display_issues if issue.level == "info")
        total_issues = len(display_issues)

        total_errors += error_count
        total_warnings += warning_count

        print_colored(f"\n项目存档 '{package_view.name}' ({package_view.package_id})", Colors.BOLD)
        if not display_issues:
            print_colored("  ✅ 未发现与资源挂载或引用关系相关的问题。", Colors.GREEN)
            continue

        print_colored(
            f"  发现 {total_issues} 个问题：错误 {error_count}，警告 {warning_count}，提示 {info_count}。",
            Colors.YELLOW,
        )

        for issue in display_issues:
            if issue.level == "error":
                icon = "❌"
                color = Colors.RED
            elif issue.level == "warning":
                icon = "⚠️"
                color = Colors.YELLOW
            else:
                icon = "ℹ️"
                color = Colors.BLUE
            location_text = issue.location or ""
            header = f"{icon} [{issue.category}] {location_text}".strip()
            print_colored(f"  {header}", color)
            print(f"     {issue.message}")
            suggestion_text = getattr(issue, "suggestion", "")
            if suggestion_text:
                print_colored(f"     💡 {suggestion_text}", Colors.CYAN)

    print()

    print_colored("=" * 70, Colors.CYAN)
    print_colored("综合结果", Colors.CYAN + Colors.BOLD)
    print_colored("=" * 70 + "\n", Colors.CYAN)

    if total_errors == 0:
        print_colored("✅ 验证通过：项目存档级校验没有错误。", Colors.GREEN + Colors.BOLD)
        if total_warnings > 0:
            print_colored(f"⚠️ 共有 {total_warnings} 条警告，请根据上文提示检查。", Colors.YELLOW)
        print()
        return 0

    print_colored(f"❌ 存在 {total_errors} 条错误（均为项目存档级问题）。", Colors.RED + Colors.BOLD)
    if total_warnings > 0:
        print_colored(f"⚠️ 同时存在 {total_warnings} 条警告。", Colors.YELLOW)
    print()
    return 1


def _run_setup_doc_links(parsed_args: argparse.Namespace, workspace_root: Path) -> int:
    from engine.resources import build_resource_index_context

    _resource_manager, package_index_manager = build_resource_index_context(workspace_root)

    package_id_filter = str(getattr(parsed_args, "package_id", "") or "").strip()
    if package_id_filter:
        package_index_manager.ensure_shared_docs_link(package_id_filter)
        print(f"已为项目存档 '{package_id_filter}' 补齐共享文档 Junction（文档/共享文档）。")
        return 0

    count = package_index_manager.ensure_shared_docs_links_for_all_packages()
    print(f"已为 {count} 个项目存档补齐共享文档 Junction（文档/共享文档）。")
    return 0


def _run_cleanup_external_dumps(parsed_args: argparse.Namespace, workspace_root: Path) -> int:
    """清理资源库下的“外部解析产物”目录（例如 `assets/资源库/存档包`）。"""
    resource_library_root = workspace_root / "assets" / "资源库"
    external_root = resource_library_root / "存档包"
    if not external_root.exists():
        print("未发现外部解析产物目录：assets/资源库/存档包（无需清理）。")
        return 0
    if not external_root.is_dir():
        raise ValueError(f"路径存在但不是目录：{external_root}")

    action = str(getattr(parsed_args, "action", "move") or "").strip().lower()
    dry_run = bool(getattr(parsed_args, "dry_run", False))
    dest_base_text = str(getattr(parsed_args, "dest", "") or "").strip() or "tmp/external_dumps"

    if action not in {"move", "delete"}:
        raise ValueError(f"未知 action: {action!r}（仅支持 move/delete）")

    if action == "delete":
        if dry_run:
            print(f"[DRY-RUN] 将删除目录：{external_root}")
            return 0
        shutil.rmtree(external_root)
        print(f"已删除外部解析产物目录：{external_root}")
        return 0

    # move
    dest_base = Path(dest_base_text)
    if not dest_base.is_absolute():
        dest_base = workspace_root / dest_base
    dest_base = dest_base.resolve()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_dir = dest_base / f"存档包_{timestamp}"
    if dest_dir.exists():
        raise ValueError(f"目标目录已存在，无法移动：{dest_dir}")

    if dry_run:
        print(f"[DRY-RUN] 将移动目录：{external_root}")
        print(f"[DRY-RUN] 目标目录：{dest_dir}")
        return 0

    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(external_root), str(dest_dir))
    print(f"已将外部解析产物移动到：{dest_dir}")
    return 0


def _run_validate_ui(parsed_args: argparse.Namespace, workspace_root: Path) -> int:
    from engine.resources import build_resource_index_context

    from app.cli.ui_variable_quickfixes import apply_ui_variable_quickfixes
    from app.cli.ui_variable_validator import format_ui_issues_text, validate_ui_source_dir

    _resource_manager, package_index_manager = build_resource_index_context(workspace_root)

    package_id_filter = str(getattr(parsed_args, "package_id", "") or "").strip()
    package_infos = package_index_manager.list_packages()
    if not package_infos:
        print("未找到任何项目存档目录（assets/资源库/项目存档/*），跳过 UI 校验。")
        return 0

    apply_fixes = bool(getattr(parsed_args, "apply_fixes", False))
    fix_dry_run = bool(getattr(parsed_args, "fix_dry_run", False))
    if apply_fixes and fix_dry_run:
        print("[ERROR] --fix 与 --fix-dry-run 不能同时使用。")
        return 1

    allowed_scopes = {"ps", "lv", "p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8"}
    all_issues: list = []
    all_fix_actions: list = []

    for info in package_infos:
        if not isinstance(info, dict):
            continue
        package_id = str(info.get("package_id") or "").strip()
        if not package_id:
            continue
        if package_id_filter and package_id_filter != package_id:
            continue

        ui_source_dir = (
            workspace_root
            / "assets"
            / "资源库"
            / "项目存档"
            / package_id
            / "管理配置"
            / "UI源码"
        )
        if apply_fixes or fix_dry_run:
            dry_run = bool(fix_dry_run) or (not bool(apply_fixes))
            all_fix_actions.extend(
                apply_ui_variable_quickfixes(
                    workspace_root=workspace_root,
                    package_id=package_id,
                    dry_run=dry_run,
                )
            )
        issues = validate_ui_source_dir(
            ui_source_dir,
            allowed_scopes=allowed_scopes,
            workspace_root=workspace_root,
            package_id=package_id,
        )
        all_issues.extend(issues)

    if all_fix_actions:
        print("=" * 80)
        print("[FIX] UI 变量自动补齐计划")
        print("=" * 80)
        for action in all_fix_actions:
            print(f"  - {action.file_path}: {action.summary}")
        if bool(fix_dry_run) or (not bool(apply_fixes)):
            print("\n[FIX] DRY-RUN：未写盘。若确认无误，请改用 --fix 执行写入。")
        print()

    print(format_ui_issues_text(all_issues))
    return 0 if not all_issues else 1


def _run_extract_ui_defaults(parsed_args: argparse.Namespace, workspace_root: Path) -> int:
    from app.cli.ui_variable_defaults_extractor import (
        extract_ui_variable_defaults_from_html,
        write_ui_variable_defaults_json_outputs,
    )

    package_id = str(getattr(parsed_args, "package_id", "") or "").strip()
    html_arg = str(getattr(parsed_args, "html", "") or "").strip()
    out_dir_arg = str(getattr(parsed_args, "out_dir", "") or "").strip()
    name_prefix = str(getattr(parsed_args, "name_prefix", "") or "").strip()

    if html_arg:
        html_path = Path(html_arg)
        if not html_path.is_absolute():
            html_path = workspace_root / html_path
        html_path = html_path.resolve()
    else:
        if not package_id:
            raise ValueError("缺少 --html；或提供 --package-id 以使用默认 HTML 路径。")
        html_path = (
            workspace_root
            / "assets"
            / "资源库"
            / "项目存档"
            / package_id
            / "管理配置"
            / "UI源码"
            / "ceshi_rect.html"
        ).resolve()

    if out_dir_arg:
        out_dir = Path(out_dir_arg)
        if not out_dir.is_absolute():
            out_dir = workspace_root / out_dir
        out_dir = out_dir.resolve()
    else:
        bucket = package_id if package_id else "_adhoc"
        out_dir = (workspace_root / "app" / "runtime" / "cache" / "ui_artifacts" / bucket / "ui_defaults").resolve()

    result = extract_ui_variable_defaults_from_html(html_path)
    raw_path, split_raw_path, split_strings_path = write_ui_variable_defaults_json_outputs(
        result=result,
        out_dir=out_dir,
        name_prefix=name_prefix,
    )

    keys = sorted(result.split_defaults.keys())
    print("=" * 80)
    print("extract-ui-defaults：完成")
    print("=" * 80)
    print(f"html: {result.html_path}")
    print(f"out_dir: {out_dir}")
    print(f"groups: {', '.join(keys) if keys else '<empty>'}")
    print()
    print(f"- raw:           {raw_path}")
    print(f"- split(raw):    {split_raw_path}")
    print(f"- split(strings):{split_strings_path}")
    print()
    return 0


def _run_audit_custom_vars(parsed_args: argparse.Namespace, workspace_root: Path) -> int:
    from engine.resources import build_resource_index_context

    from app.cli.custom_variable_usage_auditor import (
        CustomVariableAuditReport,
        collect_graph_py_files,
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
        package_graph_root = (
            workspace_root / "assets" / "资源库" / "项目存档" / package_id / "节点图"
        ).resolve()
        graph_roots: list[Path] = [shared_graph_root, package_graph_root]
        graph_roots = [p for p in graph_roots if p.is_dir()]

        py_files = collect_graph_py_files(graph_roots)
        usages = scan_custom_variable_usages(py_files)
        report = CustomVariableAuditReport(
            graph_roots=[p.as_posix() for p in graph_roots],
            scanned_files=len(py_files),
            usages=usages,
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


def _run_validate_all(parsed_args: argparse.Namespace, workspace_root: Path) -> int:
    package_id_filter = str(getattr(parsed_args, "package_id", "") or "").strip()
    apply_fixes = bool(getattr(parsed_args, "apply_fixes", False))
    fix_dry_run = bool(getattr(parsed_args, "fix_dry_run", False))
    fail_on_warning = bool(getattr(parsed_args, "fail_on_warning", False))
    if apply_fixes and fix_dry_run:
        print("[ERROR] --fix 与 --fix-dry-run 不能同时使用。")
        return 1

    # 复用同一套 CLI parser 生成各子命令 namespace，避免复制 validate-graphs 的参数默认值。
    common_args: list[str] = []
    if package_id_filter:
        common_args.extend(["--package-id", package_id_filter])
    if apply_fixes:
        common_args.append("--fix")
    if fix_dry_run:
        common_args.append("--fix-dry-run")

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
    ns_project = _parse_cli(["validate-project", *common_args])
    code_project = _run_validate_package(ns_project, workspace_root)

    # 2) UI 源码：变量占位符/来源闭包
    ns_ui = _parse_cli(["validate-ui", *common_args])
    code_ui = _run_validate_ui(ns_ui, workspace_root)

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
    failed = [(name, code) for name, code in [("validate-project", code_project), ("validate-ui", code_ui), ("validate-graphs", code_graphs)] if code != 0]
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


def main(argv: Sequence[str] | None = None) -> int:
    _install_utf8_streams_on_windows()

    argv_list: Sequence[str] = sys.argv[1:] if argv is None else argv
    parsed_args = _parse_cli(argv_list)

    workspace_root_text = str(parsed_args.workspace_root).strip() if hasattr(parsed_args, "workspace_root") else ""
    workspace_root = resolve_workspace_root(workspace_root_text if workspace_root_text else None, start_paths=[Path(__file__).resolve()])

    os.chdir(workspace_root)

    from engine.configs.settings import settings

    # 工具入口默认开启信息级日志，确保用户可见关键进度（与 CLI 约定一致）。
    # 例外：validate-graphs 的 --json 模式要求 stdout 仅输出 JSON（便于脚本/CI 消费），
    # 因此需关闭 info 日志避免混入前置文本。
    enable_info_logs = True
    if parsed_args.command == "validate-graphs" and bool(getattr(parsed_args, "output_json", False)):
        enable_info_logs = False
    settings.NODE_IMPL_LOG_VERBOSE = bool(enable_info_logs)
    init_settings_for_workspace(workspace_root=workspace_root, load_user_settings=False)

    if parsed_args.command == "print-workspace":
        print(f"workspace_root: {workspace_root}")
        print(f"assets_dir:     {workspace_root / 'assets'}")
        return 0

    if parsed_args.command == "validate-graphs":
        return _run_validate_graphs(parsed_args, workspace_root)

    if parsed_args.command == "validate-file":
        return _run_validate_file(parsed_args, workspace_root)

    if parsed_args.command in {"validate-project", "validate-package"}:
        return _run_validate_package(parsed_args, workspace_root)

    if parsed_args.command == "setup-doc-links":
        return _run_setup_doc_links(parsed_args, workspace_root)

    if parsed_args.command == "cleanup-external-dumps":
        return _run_cleanup_external_dumps(parsed_args, workspace_root)

    if parsed_args.command == "validate-ui":
        return _run_validate_ui(parsed_args, workspace_root)

    if parsed_args.command == "extract-ui-defaults":
        return _run_extract_ui_defaults(parsed_args, workspace_root)

    if parsed_args.command == "audit-custom-vars":
        return _run_audit_custom_vars(parsed_args, workspace_root)

    if parsed_args.command == "apply-ui-defaults":
        from app.cli.ui_variable_defaults_applier import (
            apply_ui_variable_defaults_to_level_variables,
            apply_ui_variable_defaults_to_level_variables_from_ui_source_dir,
        )

        package_id = str(getattr(parsed_args, "package_id", "") or "").strip()
        html_arg = str(getattr(parsed_args, "html", "") or "").strip()
        dry_run = bool(getattr(parsed_args, "dry_run", False))
        scan_all = bool(getattr(parsed_args, "all", False))
        prune_managed_keys = bool(getattr(parsed_args, "prune_managed_keys", False))

        if scan_all:
            ui_source_dir = (
                Path("assets")
                / "资源库"
                / "项目存档"
                / package_id
                / "管理配置"
                / "UI源码"
            )
            actions = apply_ui_variable_defaults_to_level_variables_from_ui_source_dir(
                workspace_root=workspace_root,
                package_id=package_id,
                ui_source_dir=ui_source_dir,
                dry_run=dry_run,
                prune_managed_keys=prune_managed_keys,
            )
        else:
            if html_arg:
                html_path = Path(html_arg)
            else:
                html_path = (
                    Path("assets")
                    / "资源库"
                    / "项目存档"
                    / package_id
                    / "管理配置"
                    / "UI源码"
                    / "ceshi_rect.html"
                )
            actions = apply_ui_variable_defaults_to_level_variables(
                workspace_root=workspace_root,
                package_id=package_id,
                html_path=html_path,
                dry_run=dry_run,
            )
        print("=" * 80)
        print("apply-ui-defaults：完成")
        print("=" * 80)
        for action in actions:
            print(f"- {action.file_path}: {action.summary}")
        print()
        return 0

    if parsed_args.command == "validate-all":
        return _run_validate_all(parsed_args, workspace_root)

    raise SystemExit(f"未知命令: {parsed_args.command}")


if __name__ == "__main__":
    sys.exit(main())


