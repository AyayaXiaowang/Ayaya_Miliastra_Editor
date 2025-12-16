"""
统一引擎版 节点图验证 CLI（推荐入口）

【职责定位】
本脚本为 CLI 包装层，仅负责：
1. 命令行参数解析（文件收集、开关处理）
2. 调用 `engine.validate.validate_files` 执行验证
3. 按文件与目录分组输出结果，并提供错误摘要

核心验证逻辑完全由 `engine.validate` 提供，本脚本不实现任何验证规则。

【设计边界】
- 脚本及引擎只做 Graph Code 与节点图的静态语法/结构/连线校验，不会执行任何节点实现代码，也不尝试模拟运行逻辑。
- 校验关注“节点是否存在、端口是否匹配、连线是否合理”等问题，目标是在写代码阶段就能看到错误提示。

用法示例：
  - 全量（节点图 + 复合节点）：
      python -X utf8 tools/validate/validate_graphs.py --all
  - 常用单文件：
      python -X utf8 tools/validate/validate_graphs.py -f assets/资源库/节点图/server/某图.py
  - 目录或通配符：
      python -X utf8 tools/validate/validate_graphs.py assets/资源库/节点图/server
      python -X utf8 tools/validate/validate_graphs.py "assets/资源库/节点图/**/*.py"
  - 行为开关：实体入参严格模式（仅允许连线/事件参数）
      python -X utf8 tools/validate/validate_graphs.py --all --strict
"""

from __future__ import annotations

import argparse
import glob
import io
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

# 工作空间根目录（脚本位于 tools/validate/ 下）
WORKSPACE = Path(__file__).resolve().parents[2]

# Windows 控制台输出编码为 UTF-8
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")  # type: ignore[attr-defined]

# 导入引擎
if not __package__:
    raise SystemExit(
        "请从项目根目录使用模块方式运行：\n"
        "  python -X utf8 -m tools.validate.validate_graphs --all\n"
        "（不再支持通过脚本内 sys.path.insert 的方式运行）"
    )

from engine.validate import EngineIssue, validate_files  # noqa: E402
from engine.configs.settings import settings  # noqa: E402

# 为布局/注册表上下文等依赖 workspace_root 的模块提供入口信息
settings.set_config_path(WORKSPACE)


def _normalize_slash(text: str) -> str:
    return text.replace("\\", "/")


def _relative_path_for_display(path: Path, workspace: Path) -> str:
    resolved_path = path.resolve()
    resolved_workspace = workspace.resolve()
    resolved_path_text = _normalize_slash(str(resolved_path))
    resolved_workspace_text = _normalize_slash(str(resolved_workspace))
    prefix = resolved_workspace_text + "/"
    if resolved_path_text.startswith(prefix):
        return resolved_path_text[len(prefix):]
    return resolved_path_text


def _normalize_issue_path(issue_file: str | None, workspace: Path) -> str:
    if not issue_file:
        return "<unknown>"
    normalized_text = _normalize_slash(issue_file)
    workspace_text = _normalize_slash(str(workspace.resolve()))
    prefix = workspace_text + "/"
    if normalized_text.startswith(prefix):
        return normalized_text[len(prefix):]
    return normalized_text


def _collect_all_targets(workspace: Path) -> List[Path]:
    files: List[Path] = []
    graphs_dir = workspace / "assets" / "资源库" / "节点图"
    composites_dir = workspace / "assets" / "资源库" / "复合节点库"
    if graphs_dir.exists():
        files.extend(
            sorted(
                path
                for path in graphs_dir.rglob("*.py")
                if not path.name.startswith("_")
            )
        )
    if composites_dir.exists():
        files.extend(
            sorted(
                path
                for path in composites_dir.rglob("*.py")
                if path.name.startswith("composite_")
            )
        )
    return files


def _expand_target_to_files(target_text: str, workspace: Path) -> List[Path]:
    trimmed = target_text.strip()
    if not trimmed:
        return []
    contains_glob = ("*" in trimmed) or ("?" in trimmed) or ("[" in trimmed)
    raw_path = Path(trimmed)

    if contains_glob:
        if raw_path.is_absolute():
            return [Path(match) for match in glob.glob(trimmed, recursive=True) if Path(match).is_file()]
        return [match for match in workspace.glob(trimmed) if match.is_file()]

    absolute_path = raw_path if raw_path.is_absolute() else workspace / raw_path
    if not absolute_path.exists():
        print(f"[ERROR] 文件或目录不存在: {absolute_path}")
        sys.exit(1)
    if absolute_path.is_dir():
        collected = sorted(absolute_path.rglob("*.py"))
    else:
        collected = [absolute_path]

    graphs_dir = (workspace / "assets" / "资源库" / "节点图").resolve()
    composites_dir = (workspace / "assets" / "资源库" / "复合节点库").resolve()
    filtered: List[Path] = []
    for path in collected:
        try:
            _ = path.resolve().relative_to(graphs_dir)
        except ValueError:
            pass
        else:
            if path.name.startswith("_"):
                continue
            filtered.append(path)
            continue

        try:
            _ = path.resolve().relative_to(composites_dir)
        except ValueError:
            filtered.append(path)
            continue
        if not path.name.startswith("composite_"):
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


def _resolve_targets(parsed_args: argparse.Namespace, workspace: Path) -> List[Path]:
    requested_targets: List[str] = list(parsed_args.targets) + list(parsed_args.single_files)
    if parsed_args.validate_all or not requested_targets:
        return _collect_all_targets(workspace)

    collected: List[Path] = []
    for target_text in requested_targets:
        collected.extend(_expand_target_to_files(target_text, workspace))

    if not collected:
        description = "assets/资源库/{节点图,复合节点库}/**/*.py" if not requested_targets else ", ".join(requested_targets)
        print(f"[ERROR] 未找到匹配的文件: {description}")
        sys.exit(1)
    return _deduplicate_preserve_order(collected)


def _group_issues_by_file(issues: List[EngineIssue], workspace: Path) -> Dict[str, List[EngineIssue]]:
    grouped: Dict[str, List[EngineIssue]] = {}
    for issue in issues:
        relative_text = _normalize_issue_path(issue.file, workspace)
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
    issues_by_file: Dict[str, List[EngineIssue]],
    workspace: Path,
) -> Dict[str, Dict[str, int]]:
    stats: Dict[str, Dict[str, int]] = {}
    for target_path in targets:
        relative_text = _relative_path_for_display(target_path, workspace)
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


def _build_issue_summary(issues: List[EngineIssue]) -> tuple[Counter[str], Counter[str], Counter[str]]:
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
    issues_by_file: Dict[str, List[EngineIssue]],
    workspace: Path,
) -> int:
    failed_files = 0
    sorted_targets = sorted(targets, key=lambda path: _relative_path_for_display(path, workspace))
    for target_path in sorted_targets:
        relative_text = _relative_path_for_display(target_path, workspace)
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


def parse_cli(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="节点图 / 复合节点验证入口（engine.validate）",
        formatter_class=argparse.RawTextHelpFormatter,
    )
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
        help="常用单文件校验入口，可重复，例如 -f assets/资源库/节点图/server_x.py",
    )
    parser.add_argument(
        "--all",
        dest="validate_all",
        action="store_true",
        help="校验 assets/资源库/节点图 与 assets/资源库/复合节点库 全量",
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
    return parser.parse_args(argv)


def main() -> None:
    parsed_args = parse_cli(sys.argv[1:])
    targets = _resolve_targets(parsed_args, WORKSPACE)

    print("=" * 80)
    mode_desc = "STRICT" if parsed_args.strict_entity_wire_only else "DEFAULT"
    print(f"开始验证 {len(targets)} 个文件（模式: {mode_desc}）...")
    print("=" * 80)
    print()

    report = validate_files(
        targets,
        WORKSPACE,
        strict_entity_wire_only=parsed_args.strict_entity_wire_only,
        use_cache=not parsed_args.disable_cache,
    )

    issues_by_file = _group_issues_by_file(report.issues, WORKSPACE)
    failed_files = _print_file_details(targets, issues_by_file, WORKSPACE)
    folder_stats = _build_folder_stats(targets, issues_by_file, WORKSPACE)
    level_counts, category_counts, code_counts = _build_issue_summary(report.issues)

    _print_summary(len(targets), failed_files, folder_stats, level_counts, category_counts, code_counts)

    if failed_files > 0:
        sys.exit(1)
    print("\n[SUCCESS] 所有文件通过（引擎）")
    sys.exit(0)


if __name__ == "__main__":
    main()

