from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path


def register_project_tools_commands(subparsers: argparse._SubParsersAction) -> None:
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
    validate_package_parser.set_defaults(_runner=run_validate_project)

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
    validate_package_legacy_parser.set_defaults(_runner=run_validate_project)

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
    setup_doc_links_parser.set_defaults(_runner=run_setup_doc_links)

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
    cleanup_dumps_parser.set_defaults(_runner=run_cleanup_external_dumps)


def run_validate_project(parsed_args: argparse.Namespace, workspace_root: Path) -> int:
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
        "自定义变量注册表",
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


def run_setup_doc_links(parsed_args: argparse.Namespace, workspace_root: Path) -> int:
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


def run_cleanup_external_dumps(parsed_args: argparse.Namespace, workspace_root: Path) -> int:
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

