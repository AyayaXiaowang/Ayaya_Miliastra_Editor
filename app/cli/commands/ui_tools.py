from __future__ import annotations

import argparse
from pathlib import Path


def register_ui_tools_commands(subparsers: argparse._SubParsersAction) -> None:
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
    validate_ui_parser.set_defaults(_runner=run_validate_ui)

    ui_var_parser = subparsers.add_parser(
        "ui-var",
        help="查询某个自定义变量是否被 UI源码 引用（并列出引用它的 HTML 文件）",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    ui_var_parser.add_argument(
        "--package-id",
        required=True,
        help=(
            "项目存档 package_id（扫描：assets/资源库/项目存档/<package_id>/管理配置/UI源码；"
            "默认同时扫描共享 UI源码）。"
        ),
    )
    ui_var_parser.add_argument(
        "expr",
        help=(
            "变量名或 UI 表达式：\n"
            "- UI战斗_文本\n"
            "- lv.UI战斗_文本\n"
            "- lv.UI战斗_文本.压岁钱\n"
            "- ps.ui_vote\n"
            "- p1.ui_vote\n"
        ),
    )
    ui_var_parser.add_argument(
        "--no-shared",
        action="store_true",
        help="不扫描共享 UI源码（assets/资源库/共享/管理配置/UI源码）。",
    )
    ui_var_parser.add_argument(
        "--show-locations",
        action="store_true",
        help="输出每个引用点的 line:column（更像 grep）。",
    )
    ui_var_parser.add_argument(
        "--json",
        dest="output_json",
        action="store_true",
        help="仅输出 JSON（stdout 只输出 JSON，便于脚本/CI 消费）。",
    )
    ui_var_parser.set_defaults(_runner=run_ui_var)

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
        help=("输出目录（可相对 workspace_root）。默认写入运行时缓存 ui_artifacts 目录，避免污染资源库。"),
    )
    extract_ui_defaults_parser.add_argument(
        "--name-prefix",
        default="",
        help="输出文件名前缀（可用于区分多次导出）。",
    )
    extract_ui_defaults_parser.set_defaults(_runner=run_extract_ui_defaults)

    apply_ui_defaults_parser = subparsers.add_parser(
        "apply-ui-defaults",
        help="将 UI HTML 的 data-ui-variable-defaults 一键写入注册表默认值（写到 自定义变量注册表.py）",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    apply_ui_defaults_parser.add_argument(
        "--package-id",
        required=True,
        help="项目存档 package_id（目标写入：assets/资源库/项目存档/<package_id>/管理配置/关卡变量/自定义变量注册表.py）",
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
    apply_ui_defaults_parser.set_defaults(_runner=run_apply_ui_defaults)

    sync_ui_vars_parser = subparsers.add_parser(
        "sync-ui-vars",
        help="一键同步 UI 变量：validate-ui + apply-ui-defaults --all（若存在 defaults）+ validate-ui",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    sync_ui_vars_parser.add_argument(
        "--package-id",
        required=True,
        help="项目存档 package_id（目标：assets/资源库/项目存档/<package_id>/管理配置/UI源码 与 关卡变量）。",
    )
    sync_ui_vars_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览同步动作：apply-ui-defaults 走 --dry-run（不写盘）。",
    )
    sync_ui_vars_parser.set_defaults(_runner=run_sync_ui_vars)


def run_validate_ui(parsed_args: argparse.Namespace, workspace_root: Path) -> int:
    from engine.resources import build_resource_index_context

    from app.cli.ui_variable_validator import format_ui_issues_text, validate_ui_source_dir

    _resource_manager, package_index_manager = build_resource_index_context(workspace_root)

    package_id_filter = str(getattr(parsed_args, "package_id", "") or "").strip()
    package_infos = package_index_manager.list_packages()
    if not package_infos:
        print("未找到任何项目存档目录（assets/资源库/项目存档/*），跳过 UI 校验。")
        return 0

    allowed_scopes = {"ps", "lv", "p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8"}
    all_issues: list = []

    for info in package_infos:
        if not isinstance(info, dict):
            continue
        package_id = str(info.get("package_id") or "").strip()
        if not package_id:
            continue
        if package_id_filter and package_id_filter != package_id:
            continue

        ui_source_dir = (
            workspace_root / "assets" / "资源库" / "项目存档" / package_id / "管理配置" / "UI源码"
        )
        issues = validate_ui_source_dir(
            ui_source_dir,
            allowed_scopes=allowed_scopes,
            workspace_root=workspace_root,
            package_id=package_id,
        )
        all_issues.extend(issues)

    print(format_ui_issues_text(all_issues))
    return 0 if not all_issues else 1


def run_ui_var(parsed_args: argparse.Namespace, workspace_root: Path) -> int:
    from app.cli.ui_var_query import (
        format_ui_var_query_result_text,
        query_ui_var_usage,
        serialize_ui_var_query_result_json,
    )

    package_id = str(getattr(parsed_args, "package_id", "") or "").strip()
    expr = str(getattr(parsed_args, "expr", "") or "").strip()
    include_shared = not bool(getattr(parsed_args, "no_shared", False))
    show_locations = bool(getattr(parsed_args, "show_locations", False))
    output_json = bool(getattr(parsed_args, "output_json", False))

    result = query_ui_var_usage(
        workspace_root=workspace_root,
        package_id=package_id,
        expr=expr,
        include_shared=include_shared,
    )

    if output_json:
        print(serialize_ui_var_query_result_json(result))
        return 0

    print(format_ui_var_query_result_text(result, show_locations=show_locations))
    return 0


def run_extract_ui_defaults(parsed_args: argparse.Namespace, workspace_root: Path) -> int:
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


def run_apply_ui_defaults(parsed_args: argparse.Namespace, workspace_root: Path) -> int:
    from app.cli.ui_variable_defaults_registry_applier import apply_ui_defaults_to_registry

    package_id = str(getattr(parsed_args, "package_id", "") or "").strip()
    html_arg = str(getattr(parsed_args, "html", "") or "").strip()
    dry_run = bool(getattr(parsed_args, "dry_run", False))
    scan_all = bool(getattr(parsed_args, "all", False))

    if scan_all:
        actions = apply_ui_defaults_to_registry(
            workspace_root=workspace_root,
            package_id=package_id,
            html_path=None,
            apply_all=True,
            dry_run=dry_run,
        )
    else:
        if html_arg:
            html_path = Path(html_arg).resolve()
        else:
            html_path = None
        actions = apply_ui_defaults_to_registry(
            workspace_root=workspace_root,
            package_id=package_id,
            html_path=html_path,
            apply_all=False,
            dry_run=dry_run,
        )
    print("=" * 80)
    print("apply-ui-defaults：完成")
    print("=" * 80)
    for action in actions:
        print(f"- {action.file_path}: {action.summary}")
    print()
    return 0


def _ui_source_dir_has_ui_defaults(ui_source_dir: Path) -> bool:
    """快速判断 UI源码目录中是否存在 data-ui-variable-defaults（避免对无 defaults 的包误触发 apply-ui-defaults 抛错）。"""
    if not ui_source_dir.exists() or not ui_source_dir.is_dir():
        return False
    html_files = sorted([p for p in ui_source_dir.rglob("*.html") if p.is_file()], key=lambda p: p.as_posix())
    for html_path in html_files:
        if html_path.name.endswith(".flattened.html"):
            continue
        text = html_path.read_text(encoding="utf-8")
        if "data-ui-variable-defaults" in text:
            return True
    return False


def run_sync_ui_vars(parsed_args: argparse.Namespace, workspace_root: Path) -> int:
    """一键同步 UI 变量（命令行开发友好）：validate-ui + apply-ui-defaults --all + validate-ui。"""
    from engine.resources import build_resource_index_context

    from app.cli.ui_variable_validator import format_ui_issues_text, validate_ui_source_dir

    from app.cli.ui_variable_defaults_registry_applier import apply_ui_defaults_to_registry

    _resource_manager, package_index_manager = build_resource_index_context(workspace_root)

    package_id = str(getattr(parsed_args, "package_id", "") or "").strip()
    if not package_id:
        raise ValueError("package_id 不能为空")

    dry_run = bool(getattr(parsed_args, "dry_run", False))

    package_infos = package_index_manager.list_packages()
    if not package_infos:
        print("未找到任何项目存档目录（assets/资源库/项目存档/*），跳过。")
        return 0

    if package_id not in {str(info.get("package_id") or "").strip() for info in package_infos if isinstance(info, dict)}:
        raise ValueError(
            f"未找到指定项目存档：{package_id}（请确认 assets/资源库/项目存档/<package_id> 目录存在）。"
        )

    ui_source_dir = (
        workspace_root / "assets" / "资源库" / "项目存档" / package_id / "管理配置" / "UI源码"
    )

    print("=" * 80)
    print("sync-ui-vars：开始")
    print("=" * 80)
    print(f"- package_id: {package_id}")
    print(f"- ui_source_dir: {ui_source_dir}")
    print(f"- mode: {'DRY-RUN' if dry_run else 'APPLY'}")
    print()

    allowed_scopes = {"ps", "lv", "p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8"}
    print("=" * 80)
    print("[STEP] validate-ui")
    print("=" * 80)
    issues = validate_ui_source_dir(
        ui_source_dir,
        allowed_scopes=allowed_scopes,
        workspace_root=workspace_root,
        package_id=package_id,
    )
    print(format_ui_issues_text(issues))
    if issues:
        return 1

    # 2) apply-ui-defaults --all（若存在 defaults）
    if _ui_source_dir_has_ui_defaults(ui_source_dir):
        print("=" * 80)
        print("[STEP] apply-ui-defaults --all")
        print("=" * 80)
        actions = apply_ui_defaults_to_registry(
            workspace_root=workspace_root,
            package_id=package_id,
            html_path=None,
            apply_all=True,
            dry_run=dry_run,
        )
        for action in actions:
            print(f"- {action.file_path}: {action.summary}")
        print()
    else:
        print("[STEP] apply-ui-defaults --all：未发现任何 data-ui-variable-defaults，跳过默认值同步。\n")

    # 3) validate-ui 再跑一次（闭环）
    print("=" * 80)
    print("[STEP] validate-ui（闭环）")
    print("=" * 80)
    issues2 = validate_ui_source_dir(
        ui_source_dir,
        allowed_scopes=allowed_scopes,
        workspace_root=workspace_root,
        package_id=package_id,
    )
    print(format_ui_issues_text(issues2))
    if issues2:
        return 1

    print("=" * 80)
    print("sync-ui-vars：完成")
    print("=" * 80)
    return 0

