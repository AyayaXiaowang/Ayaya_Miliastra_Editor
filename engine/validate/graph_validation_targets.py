from __future__ import annotations

import glob
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

from engine.nodes.composite_file_policy import (
    discover_composite_definition_files,
    discover_composite_library_dirs,
    is_composite_definition_file,
)
from engine.utils.path_utils import normalize_slash
from engine.utils.resource_library_layout import discover_resource_root_directories

__all__ = [
    "GraphValidationTargetsResolution",
    "collect_default_graph_validation_targets",
    "resolve_graph_validation_targets",
    "expand_graph_validation_target_to_files",
    "find_matching_base_dir",
    "normalize_issue_path",
    "normalize_slash",
    "relative_path_for_display",
]


@dataclass(frozen=True)
class GraphValidationTargetsResolution:
    """节点图校验目标收敛结果（供 CLI/UI 包装层使用）。"""

    targets: List[Path]
    errors: List[str]

def relative_path_for_display(path: Path, workspace_root: Path) -> str:
    resolved_path = path.resolve()
    resolved_workspace = workspace_root.resolve()
    resolved_path_text = normalize_slash(str(resolved_path))
    resolved_workspace_text = normalize_slash(str(resolved_workspace))
    prefix = resolved_workspace_text + "/"
    if resolved_path_text.startswith(prefix):
        return resolved_path_text[len(prefix) :]
    return resolved_path_text


def normalize_issue_path(issue_file: str | None, workspace_root: Path) -> str:
    if not issue_file:
        return "<unknown>"
    normalized_text = normalize_slash(issue_file)
    workspace_text = normalize_slash(str(workspace_root.resolve()))
    prefix = workspace_text + "/"
    if normalized_text.startswith(prefix):
        return normalized_text[len(prefix) :]
    return normalized_text


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


def _dedupe_strings_preserve_order(values: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    unique: List[str] = []
    for value in values:
        text = str(value)
        if text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def _is_under_base_dir(path: Path, base_dir: Path) -> bool:
    path_parts = path.resolve().parts
    base_parts = base_dir.resolve().parts
    if len(path_parts) < len(base_parts):
        return False
    return path_parts[: len(base_parts)] == base_parts


def find_matching_base_dir(path: Path, base_dirs: Sequence[Path]) -> Path | None:
    """返回 path 所属的最深 base_dir（用于避免多根目录误匹配）。"""
    sorted_dirs = sorted(base_dirs, key=lambda p: len(p.resolve().parts), reverse=True)
    for base_dir in sorted_dirs:
        if _is_under_base_dir(path, base_dir):
            return base_dir
    return None


def _collect_graph_root_dirs(workspace_root: Path) -> List[Path]:
    resource_library_root = (workspace_root / "assets" / "资源库").resolve()
    resource_roots = discover_resource_root_directories(resource_library_root)
    graph_root_dirs = [(root / "节点图").resolve() for root in resource_roots]
    return graph_root_dirs


def collect_default_graph_validation_targets(workspace_root: Path) -> List[Path]:
    """收敛默认校验目标：资源库多根目录下的【节点图】+【复合节点库】。"""
    graph_root_dirs = _collect_graph_root_dirs(workspace_root)
    files: List[Path] = []
    for graph_root_dir in graph_root_dirs:
        if not graph_root_dir.exists():
            continue
        for path in sorted(graph_root_dir.rglob("*.py"), key=lambda p: str(p.as_posix()).lower()):
            if path.name.startswith("_"):
                continue
            # 跳过校验脚本（如 校验节点图.py），这些不是真正的节点图文件
            if "校验" in path.stem:
                continue
            files.append(path)
    files.extend(discover_composite_definition_files(workspace_root))
    return _deduplicate_preserve_order(files)


def expand_graph_validation_target_to_files(target_text: str, workspace_root: Path) -> GraphValidationTargetsResolution:
    trimmed = str(target_text or "").strip()
    if not trimmed:
        return GraphValidationTargetsResolution(targets=[], errors=[])

    contains_glob = ("*" in trimmed) or ("?" in trimmed) or ("[" in trimmed)
    raw_path = Path(trimmed)

    collected: List[Path] = []
    if contains_glob:
        if raw_path.is_absolute():
            collected = [Path(match) for match in glob.glob(trimmed, recursive=True) if Path(match).is_file()]
        else:
            collected = [match for match in workspace_root.glob(trimmed) if match.is_file()]
    else:
        absolute_path = raw_path if raw_path.is_absolute() else (workspace_root / raw_path)
        if not absolute_path.exists():
            absolute_display = str(absolute_path.resolve())
            return GraphValidationTargetsResolution(
                targets=[],
                errors=[f"[ERROR] 文件或目录不存在: {absolute_display}"],
            )
        if absolute_path.is_dir():
            collected = sorted(absolute_path.rglob("*.py"), key=lambda p: str(p.as_posix()).lower())
        else:
            collected = [absolute_path]

    graph_root_dirs = _collect_graph_root_dirs(workspace_root)
    composite_root_dirs = list(discover_composite_library_dirs(workspace_root))

    filtered: List[Path] = []
    for path in collected:
        matched_graph_root = find_matching_base_dir(path, graph_root_dirs)
        if matched_graph_root is not None:
            if path.name.startswith("_"):
                continue
            if "校验" in path.stem:
                continue
            filtered.append(path)
            continue

        matched_composite_root = find_matching_base_dir(path, composite_root_dirs)
        if matched_composite_root is None:
            filtered.append(path)
            continue

        if not is_composite_definition_file(path):
            continue
        filtered.append(path)

    return GraphValidationTargetsResolution(targets=filtered, errors=[])


def resolve_graph_validation_targets(
    *,
    workspace_root: Path,
    targets: Sequence[str],
    single_files: Sequence[str],
    validate_all: bool,
    empty_match_description: str = "assets/资源库/项目存档/*/{节点图,复合节点库}/**/*.py",
) -> GraphValidationTargetsResolution:
    requested_targets: List[str] = list(targets) + list(single_files)
    if bool(validate_all) or not requested_targets:
        return GraphValidationTargetsResolution(
            targets=collect_default_graph_validation_targets(workspace_root),
            errors=[],
        )

    collected: List[Path] = []
    errors: List[str] = []
    for target_text in requested_targets:
        result = expand_graph_validation_target_to_files(target_text, workspace_root)
        errors.extend(result.errors)
        collected.extend(result.targets)

    if errors:
        return GraphValidationTargetsResolution(targets=[], errors=_dedupe_strings_preserve_order(errors))

    if not collected:
        description = empty_match_description if not requested_targets else ", ".join(requested_targets)
        return GraphValidationTargetsResolution(
            targets=[],
            errors=[f"[ERROR] 未找到匹配的文件: {description}"],
        )

    return GraphValidationTargetsResolution(
        targets=_deduplicate_preserve_order(collected),
        errors=[],
    )


