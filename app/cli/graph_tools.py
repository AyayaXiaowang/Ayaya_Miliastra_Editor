from __future__ import annotations

"""
Graph_Generater 便携版工具入口（CLI）。

目标：
- 源码环境：支持 `python -X utf8 -m app.cli.graph_tools ...`
- PyInstaller 冻结环境：支持 `Graph_Generater_Tools.exe ...`（无需用户安装 Python）

约定：
- 冻结运行时默认以 exe 所在目录作为 workspace_root，并在启动阶段 chdir 到该目录；
  因此发布产物要求 `assets/` 与 exe 同级外置（用户可编辑）。
- 本工具只做静态校验/检查，不执行任何节点业务逻辑（与引擎校验边界一致）。
"""

import argparse
import glob
import io
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Sequence


if not __package__ and not getattr(sys, "frozen", False):
    raise SystemExit(
        "请从项目根目录使用模块方式运行：\n"
        "  python -X utf8 -m app.cli.graph_tools --help\n"
        "（不再支持通过脚本内 sys.path.insert 的方式运行）"
    )


def _install_utf8_streams_on_windows() -> None:
    if sys.platform != "win32":
        return
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")  # type: ignore[attr-defined]


def _resolve_workspace_root(explicit_root_text: str | None) -> Path:
    if explicit_root_text:
        candidate_root = Path(explicit_root_text).expanduser()
        if not candidate_root.is_absolute():
            candidate_root = (Path.cwd() / candidate_root)
        return candidate_root.resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _normalize_slash(text: str) -> str:
    return text.replace("\\", "/")


def _relative_path_for_display(path: Path, workspace_root: Path) -> str:
    resolved_path = path.resolve()
    resolved_workspace = workspace_root.resolve()
    resolved_path_text = _normalize_slash(str(resolved_path))
    resolved_workspace_text = _normalize_slash(str(resolved_workspace))
    prefix = resolved_workspace_text + "/"
    if resolved_path_text.startswith(prefix):
        return resolved_path_text[len(prefix) :]
    return resolved_path_text


def _normalize_issue_path(issue_file: str | None, workspace_root: Path) -> str:
    if not issue_file:
        return "<unknown>"
    normalized_text = _normalize_slash(issue_file)
    workspace_text = _normalize_slash(str(workspace_root.resolve()))
    prefix = workspace_text + "/"
    if normalized_text.startswith(prefix):
        return normalized_text[len(prefix) :]
    return normalized_text


def _collect_default_targets(workspace_root: Path) -> List[Path]:
    from engine.nodes.composite_file_policy import discover_composite_definition_files

    files: List[Path] = []
    graphs_dir = workspace_root / "assets" / "资源库" / "节点图"
    composites_dir = workspace_root / "assets" / "资源库" / "复合节点库"

    if graphs_dir.exists():
        files.extend(
            sorted(
                path
                for path in graphs_dir.rglob("*.py")
                if not path.name.startswith("_") and ("校验" not in path.stem)
            )
        )
    if composites_dir.exists():
        files.extend(discover_composite_definition_files(workspace_root))
    return files


def _expand_target_to_files(target_text: str, workspace_root: Path) -> List[Path]:
    from engine.nodes.composite_file_policy import is_composite_definition_file

    trimmed = target_text.strip()
    if not trimmed:
        return []

    contains_glob = ("*" in trimmed) or ("?" in trimmed) or ("[" in trimmed)
    raw_path = Path(trimmed)

    if contains_glob:
        if raw_path.is_absolute():
            return [Path(match) for match in glob.glob(trimmed, recursive=True) if Path(match).is_file()]
        return [match for match in workspace_root.glob(trimmed) if match.is_file()]

    absolute_path = raw_path if raw_path.is_absolute() else (workspace_root / raw_path)
    if not absolute_path.exists():
        print(f"[ERROR] 文件或目录不存在: {absolute_path}")
        sys.exit(1)

    collected: List[Path]
    if absolute_path.is_dir():
        collected = sorted(absolute_path.rglob("*.py"))
    else:
        collected = [absolute_path]

    graphs_dir = (workspace_root / "assets" / "资源库" / "节点图").resolve()
    composites_dir = (workspace_root / "assets" / "资源库" / "复合节点库").resolve()

    filtered: List[Path] = []
    for path in collected:
        resolved_path = path.resolve()
        try:
            _ = resolved_path.relative_to(graphs_dir)
        except ValueError:
            pass
        else:
            if path.name.startswith("_"):
                continue
            if "校验" in path.stem:
                continue
            filtered.append(path)
            continue

        try:
            _ = resolved_path.relative_to(composites_dir)
        except ValueError:
            filtered.append(path)
            continue
        if not is_composite_definition_file(path):
            continue
        filtered.append(path)
    return filtered


def _deduplicate_preserve_order(paths: Iterable[Path]) -> List[Path]:
    seen: set[str] = set()
    unique: List[Path] = []
    for path in paths:
        resolved_text = str(path.resolve())
        if resolved_text in seen:
            continue
        seen.add(resolved_text)
        unique.append(path)
    return unique


def _resolve_validate_graphs_targets(parsed_args: argparse.Namespace, workspace_root: Path) -> List[Path]:
    requested_targets: List[str] = list(parsed_args.targets) + list(parsed_args.single_files)
    if parsed_args.validate_all or not requested_targets:
        return _collect_default_targets(workspace_root)

    collected: List[Path] = []
    for target_text in requested_targets:
        collected.extend(_expand_target_to_files(target_text, workspace_root))

    if not collected:
        description = (
            "assets/资源库/{节点图,复合节点库}/**/*.py"
            if not requested_targets
            else ", ".join(requested_targets)
        )
        print(f"[ERROR] 未找到匹配的文件: {description}")
        sys.exit(1)
    return _deduplicate_preserve_order(collected)


def _group_issues_by_file(issues: List["EngineIssue"], workspace_root: Path) -> Dict[str, List["EngineIssue"]]:
    grouped: Dict[str, List["EngineIssue"]] = {}
    for issue in issues:
        relative_text = _normalize_issue_path(issue.file, workspace_root)
        grouped.setdefault(relative_text, []).append(issue)
    return grouped


def _folder_bucket(relative_path_text: str) -> str:
    path_obj = Path(relative_path_text)
    parts = path_obj.parts
    if len(parts) >= 3 and parts[0] == "assets" and parts[1] == "资源库":
        return str(Path(*parts[:3]))
    parent = path_obj.parent
    parent_text = str(parent)
    if parent_text == ".":
        return "<workspace>"
    return parent_text


def _build_folder_stats(
    targets: List[Path],
    issues_by_file: Dict[str, List["EngineIssue"]],
    workspace_root: Path,
) -> Dict[str, Dict[str, int]]:
    stats: Dict[str, Dict[str, int]] = {}
    for target_path in targets:
        relative_text = _relative_path_for_display(target_path, workspace_root)
        issue_list = issues_by_file.get(relative_text, [])
        bucket = _folder_bucket(relative_text)
        bucket_stats = stats.setdefault(bucket, {"files": 0, "error_files": 0, "warning_files": 0})
        bucket_stats["files"] += 1
        has_error = any(issue.level == "error" for issue in issue_list)
        has_warning = any(issue.level == "warning" for issue in issue_list)
        if has_error:
            bucket_stats["error_files"] += 1
        elif has_warning:
            bucket_stats["warning_files"] += 1
    return stats


def _build_issue_summary(
    issues: List["EngineIssue"],
) -> tuple[Counter[str], Counter[str], Counter[str]]:
    level_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    code_counts: Counter[str] = Counter()
    for issue in issues:
        level_counts[issue.level] += 1
        if issue.category:
            category_counts[issue.category] += 1
        if issue.code:
            code_counts[issue.code] += 1
    return level_counts, category_counts, code_counts


def _print_file_details(
    targets: List[Path],
    issues_by_file: Dict[str, List["EngineIssue"]],
    workspace_root: Path,
) -> int:
    failed_files = 0
    sorted_targets = sorted(targets, key=lambda path: _relative_path_for_display(path, workspace_root))
    for target_path in sorted_targets:
        relative_text = _relative_path_for_display(target_path, workspace_root)
        issue_list = issues_by_file.get(relative_text, [])
        if not issue_list:
            print(f"[OK] {relative_text}")
            continue

        error_count = len([issue for issue in issue_list if issue.level == "error"])
        warning_count = len([issue for issue in issue_list if issue.level == "warning"])
        level_label = "[FAILED]" if error_count > 0 else "[WARN]"
        print(f"{level_label} {relative_text} (errors: {error_count}, warnings: {warning_count})")
        for issue in issue_list:
            code_text = issue.code or "-"
            location_text = f" @ {issue.location}" if issue.location else ""
            print(f"  - [{issue.level}] [{issue.category}/{code_text}] {issue.message}{location_text}")
        print()
        failed_files += 1
    return failed_files


def _print_summary(
    total_files: int,
    failed_files: int,
    folder_stats: Dict[str, Dict[str, int]],
    level_counts: Counter[str],
    category_counts: Counter[str],
    code_counts: Counter[str],
) -> None:
    passed_files = total_files - failed_files
    error_count = level_counts.get("error", 0)
    warning_count = level_counts.get("warning", 0)

    print("=" * 80)
    print("验证完成:")
    print(f"  总计: {total_files} 个文件")
    print(f"  通过: {passed_files} 个")
    print(f"  失败: {failed_files} 个")
    print(f"  问题: {error_count} 错误, {warning_count} 警告")

    if folder_stats:
        print("  分布（按目录）:")
        for bucket, stat in sorted(folder_stats.items()):
            print(
                f"    - {bucket}: {stat['files']} 文件，"
                f"{stat['error_files']} 失败，{stat['warning_files']} 告警"
            )

    if category_counts:
        print("  错误摘要（按类别，Top 6）:")
        for category, count in category_counts.most_common(6):
            print(f"    - {category}: {count}")

    if code_counts:
        print("  错误摘要（按错误码，Top 8）:")
        for code, count in code_counts.most_common(8):
            print(f"    - {code}: {count}")

    print("=" * 80)


def _parse_cli(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="graph_tools",
        description="Graph_Generater 工具入口（校验/诊断）",
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
        help="校验节点图/复合节点（等价于 tools.validate.validate_graphs 的打包版入口）",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    validate_graphs_parser.add_argument(
        "targets",
        nargs="*",
        help="待校验的文件、通配符或目录；为空或 --all 时校验节点图与复合节点库全量",
    )
    validate_graphs_parser.add_argument(
        "-f",
        "--file",
        dest="single_files",
        action="append",
        default=[],
        help="常用单文件校验入口，可重复，例如 -f assets/资源库/节点图/server_x.py",
    )
    validate_graphs_parser.add_argument(
        "--all",
        dest="validate_all",
        action="store_true",
        help="校验 assets/资源库/节点图 与 assets/资源库/复合节点库 全量",
    )
    validate_graphs_parser.add_argument(
        "--strict",
        "--strict-entity-wire-only",
        dest="strict_entity_wire_only",
        action="store_true",
        help="实体入参严格模式，仅允许连线/事件参数",
    )
    validate_graphs_parser.add_argument(
        "--no-cache",
        dest="disable_cache",
        action="store_true",
        help="禁用校验缓存（默认启用）",
    )
    validate_graphs_parser.add_argument(
        "--no-composite-struct-check",
        dest="disable_composite_struct_check",
        action="store_true",
        help="禁用复合节点结构校验（默认启用；用于对齐UI的“缺少数据来源/未连接”等检查）",
    )

    validate_file_parser = subparsers.add_parser(
        "validate-file",
        help="校验单个节点图文件（输出与节点图脚本自检类似的通过/错误/警告列表）",
    )
    validate_file_parser.add_argument(
        "file",
        help="节点图文件路径（可相对 workspace_root）",
    )

    subparsers.add_parser(
        "print-workspace",
        help="打印当前解析到的 workspace_root 与 assets 路径（用于排查路径问题）",
    )

    return parser.parse_args(list(argv))


def _run_validate_graphs(parsed_args: argparse.Namespace, workspace_root: Path) -> int:
    from engine.validate import EngineIssue, collect_composite_structural_issues, validate_files

    targets = _resolve_validate_graphs_targets(parsed_args, workspace_root)

    print("=" * 80)
    mode_desc = "STRICT" if parsed_args.strict_entity_wire_only else "DEFAULT"
    print(f"开始验证 {len(targets)} 个文件（模式: {mode_desc}）...")
    print(f"workspace_root: {workspace_root}")
    print("=" * 80)
    print()

    report = validate_files(
        targets,
        workspace_root,
        strict_entity_wire_only=parsed_args.strict_entity_wire_only,
        use_cache=not parsed_args.disable_cache,
    )

    all_issues: List[EngineIssue] = list(report.issues)
    if not parsed_args.disable_composite_struct_check:
        all_issues.extend(collect_composite_structural_issues(targets, workspace_root))

    issues_by_file = _group_issues_by_file(all_issues, workspace_root)
    failed_files = _print_file_details(targets, issues_by_file, workspace_root)
    folder_stats = _build_folder_stats(targets, issues_by_file, workspace_root)
    level_counts, category_counts, code_counts = _build_issue_summary(all_issues)

    _print_summary(len(targets), failed_files, folder_stats, level_counts, category_counts, code_counts)

    if failed_files > 0:
        return 1
    print("\n[SUCCESS] 所有文件通过（引擎）")
    return 0


def _run_validate_file(parsed_args: argparse.Namespace, workspace_root: Path) -> int:
    from engine.validate import validate_file as validate_node_graph_file

    raw_path = Path(parsed_args.file)
    target_path = raw_path if raw_path.is_absolute() else (workspace_root / raw_path)
    target_path = target_path.resolve()

    passed, errors, warnings = validate_node_graph_file(target_path)

    print("=" * 80)
    print("节点图自检:")
    print(f"文件: {target_path}")
    print(f"结果: {'通过' if passed else '未通过'}")
    if errors:
        print("\n错误明细:")
        for index, message in enumerate(errors, start=1):
            print(f"  [{index}] {message}")
    if warnings:
        print("\n警告明细:")
        for index, message in enumerate(warnings, start=1):
            print(f"  [{index}] {message}")
    print("=" * 80)

    return 0 if passed else 1


def main(argv: Sequence[str] | None = None) -> int:
    _install_utf8_streams_on_windows()

    argv_list: Sequence[str] = sys.argv[1:] if argv is None else argv
    parsed_args = _parse_cli(argv_list)

    workspace_root_text = str(parsed_args.workspace_root).strip() if hasattr(parsed_args, "workspace_root") else ""
    workspace_root = _resolve_workspace_root(workspace_root_text if workspace_root_text else None)

    os.chdir(workspace_root)

    from engine.configs.settings import settings

    # 工具入口默认开启信息级日志，确保用户可见关键进度（与 CLI 约定一致）
    settings.NODE_IMPL_LOG_VERBOSE = True
    settings.set_config_path(workspace_root)

    if parsed_args.command == "print-workspace":
        print(f"workspace_root: {workspace_root}")
        print(f"assets_dir:     {workspace_root / 'assets'}")
        return 0

    if parsed_args.command == "validate-graphs":
        return _run_validate_graphs(parsed_args, workspace_root)

    if parsed_args.command == "validate-file":
        return _run_validate_file(parsed_args, workspace_root)

    raise SystemExit(f"未知命令: {parsed_args.command}")


if __name__ == "__main__":
    sys.exit(main())


