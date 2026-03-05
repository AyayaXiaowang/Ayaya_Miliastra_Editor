from __future__ import annotations

"""
节点图校验 CLI 输出辅助（共享模块）。

设计目标：
- 复用 `engine.validate.graph_validation_targets` 的路径归一化规则，避免 UI/CLI 在“相对路径显示、分组键”上漂移；
- 为 `app.cli.graph_tools validate-graphs` 提供统一的：
  - issues 按文件分组
  - 目录统计
  - 文本输出
  - JSON 报告 payload 构建（由调用侧决定是否打印）

注意：
- 本模块只做“报告组织与输出格式化”，不包含任何校验规则实现。
"""

from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from engine.utils.path_utils import normalize_slash

from .graph_validation_targets import (
    normalize_issue_path,
    relative_path_for_display,
)
from .issue import EngineIssue

__all__ = [
    "group_issues_by_file",
    "build_folder_stats",
    "build_issue_summary",
    "print_file_details",
    "print_summary",
    "sorted_issues_for_json",
    "build_validate_graphs_json_report",
]


def group_issues_by_file(issues: Sequence[EngineIssue], workspace_root: Path) -> Dict[str, List[EngineIssue]]:
    grouped: Dict[str, List[EngineIssue]] = {}
    for issue in issues:
        relative_text = normalize_issue_path(issue.file, workspace_root)
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


def build_folder_stats(
    targets: Sequence[Path],
    issues_by_file: Mapping[str, Sequence[EngineIssue]],
    workspace_root: Path,
) -> Dict[str, Dict[str, int]]:
    stats: Dict[str, Dict[str, int]] = {}
    for target_path in targets:
        relative_text = relative_path_for_display(target_path, workspace_root)
        issue_list = list(issues_by_file.get(relative_text, []))
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


def build_issue_summary(
    issues: Sequence[EngineIssue],
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


def _build_issue_location_text(
    issue: EngineIssue,
    *,
    include_line_span: bool,
    include_location: bool,
    include_port: bool,
) -> str:
    location_parts: List[str] = []
    if include_line_span and issue.line_span:
        location_parts.append(str(issue.line_span))
    if include_location and issue.location:
        location_parts.append(str(issue.location))
    if include_port and issue.port:
        location_parts.append(f"端口:{issue.port}")
    if not location_parts:
        return ""
    return f" @ {' | '.join(location_parts)}"


def print_file_details(
    targets: Sequence[Path],
    issues_by_file: Mapping[str, Sequence[EngineIssue]],
    workspace_root: Path,
    *,
    include_line_span: bool = True,
    include_location: bool = True,
    include_port: bool = True,
) -> int:
    failed_files = 0

    def target_sort_key(target_path: Path) -> str:
        return relative_path_for_display(target_path, workspace_root)

    sorted_targets = sorted(targets, key=target_sort_key)
    for target_path in sorted_targets:
        relative_text = relative_path_for_display(target_path, workspace_root)
        issue_list = list(issues_by_file.get(relative_text, []))
        if not issue_list:
            print(f"[OK] {relative_text}")
            continue

        error_count = len([issue for issue in issue_list if issue.level == "error"])
        warning_count = len([issue for issue in issue_list if issue.level == "warning"])
        level_label = "[FAILED]" if error_count > 0 else "[WARN]"
        print(f"{level_label} {relative_text} (errors: {error_count}, warnings: {warning_count})")
        for issue in issue_list:
            code_text = issue.code or "-"
            location_text = _build_issue_location_text(
                issue,
                include_line_span=include_line_span,
                include_location=include_location,
                include_port=include_port,
            )
            print(f"  - [{issue.level}] [{issue.category}/{code_text}] {issue.message}{location_text}")
        print()
        failed_files += 1
    return failed_files


def print_summary(
    total_files: int,
    files_with_issues: int,
    folder_stats: Mapping[str, Mapping[str, int]],
    level_counts: Counter[str],
    category_counts: Counter[str],
    code_counts: Counter[str],
    *,
    annotate_legacy_packages_bucket: bool = False,
) -> None:
    error_files = 0
    warning_files = 0
    for stat in folder_stats.values():
        error_files += int(stat.get("error_files", 0) or 0)
        warning_files += int(stat.get("warning_files", 0) or 0)
    files_with_issues = int(files_with_issues or 0)
    ok_files = total_files - error_files - warning_files
    error_count = level_counts.get("error", 0)
    warning_count = level_counts.get("warning", 0)

    print("=" * 80)
    print("验证完成:")
    print(f"  总计: {total_files} 个文件")
    print(f"  通过: {ok_files} 个")
    print(f"  告警: {warning_files} 个")
    print(f"  失败: {error_files} 个")
    print(f"  问题: {error_count} 错误, {warning_count} 警告")

    if folder_stats:
        print("  分布（按目录）:")
        packages_bucket = str(Path("assets", "资源库", "项目存档"))
        for bucket, stat in sorted(folder_stats.items()):
            display_bucket = str(bucket)
            if annotate_legacy_packages_bucket and display_bucket == packages_bucket:
                display_bucket = f"{display_bucket}（项目存档根）"
            print(
                f"    - {display_bucket}: {stat.get('files', 0)} 文件，"
                f"{stat.get('error_files', 0)} 失败，{stat.get('warning_files', 0)} 告警"
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


def _level_priority(level: str) -> int:
    if level == "error":
        return 0
    if level == "warning":
        return 1
    if level == "info":
        return 2
    return 99


def sorted_issues_for_json(issues: Sequence[EngineIssue], workspace_root: Path) -> List[Dict[str, Any]]:
    def issue_sort_key(issue: EngineIssue) -> tuple:
        return (
            normalize_issue_path(issue.file, workspace_root),
            _level_priority(issue.level),
            issue.category or "",
            issue.code or "",
            issue.line_span or "",
            issue.message or "",
            issue.location or "",
            issue.port or "",
            issue.node_id or "",
        )

    normalized: List[Dict[str, Any]] = []
    for issue in sorted(list(issues), key=issue_sort_key):
        issue_dict = issue.to_dict()
        issue_dict["file"] = normalize_issue_path(issue.file, workspace_root)
        normalized.append(issue_dict)
    return normalized


def build_validate_graphs_json_report(
    *,
    schema: str,
    schema_version: int,
    targets: Sequence[Path],
    issues: Sequence[EngineIssue],
    issues_by_file: Mapping[str, Sequence[EngineIssue]],
    workspace_root: Path,
    mode_desc: str,
    strict_entity_wire_only: bool,
    disable_cache: bool,
    disable_composite_struct_check: bool,
    folder_stats: Mapping[str, Mapping[str, int]],
    level_counts: Counter[str],
    category_counts: Counter[str],
    code_counts: Counter[str],
) -> Dict[str, Any]:
    total_files = len(targets)
    files_with_issues = 0
    files_with_errors = 0
    files_with_warnings = 0
    for target_path in targets:
        relative_text = relative_path_for_display(target_path, workspace_root)
        issue_list = list(issues_by_file.get(relative_text, []))
        if not issue_list:
            continue
        files_with_issues += 1
        if any(issue.level == "error" for issue in issue_list):
            files_with_errors += 1
        else:
            files_with_warnings += 1

    return {
        "schema": str(schema),
        "schema_version": int(schema_version),
        "workspace_root": normalize_slash(str(workspace_root.resolve())),
        "mode": str(mode_desc),
        "options": {
            "strict_entity_wire_only": bool(strict_entity_wire_only),
            "use_cache": bool(not disable_cache),
            "composite_struct_check": bool(not disable_composite_struct_check),
        },
        "targets": [
            relative_path_for_display(path, workspace_root)
            for path in sorted(list(targets), key=str)
        ],
        "stats": {
            "total_files": total_files,
            "passed_files": total_files - files_with_issues,
            "files_with_issues": files_with_issues,
            "files_with_errors": files_with_errors,
            "files_with_warnings": files_with_warnings,
            "issues_by_level": dict(level_counts),
            "issues_by_category": dict(category_counts),
            "issues_by_code": dict(code_counts),
            "folders": dict(folder_stats),
        },
        "issues": sorted_issues_for_json(issues, workspace_root),
    }


