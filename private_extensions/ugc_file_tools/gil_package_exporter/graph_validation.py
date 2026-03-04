from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional


def _find_graph_generater_root_from_output_package_root(
    output_package_root: Path,
) -> Optional[Path]:
    for parent in [output_package_root, *output_package_root.parents]:
        if (parent / "engine").is_dir() and (parent / "assets").is_dir() and (parent / "tools").is_dir():
            return parent

    from ugc_file_tools.repo_paths import try_find_graph_generater_root

    return try_find_graph_generater_root()


def _validate_graph_generater_single_package(
    graph_generater_root: Path,
    package_id: str,
) -> Dict[str, Any]:
    graph_root_text = str(graph_generater_root.resolve())
    if graph_root_text not in sys.path:
        sys.path.insert(0, graph_root_text)

    from engine.resources import build_resource_index_context
    from engine.resources.package_view import PackageView
    from engine.validate import ComprehensiveValidator

    resource_manager, package_index_manager = build_resource_index_context(graph_generater_root.resolve())
    resource_manager.rebuild_index(active_package_id=package_id)
    package_index_manager.invalidate_package_index_cache(package_id)
    package_index = package_index_manager.load_package_index(package_id)
    if package_index is None:
        raise ValueError(f"无法加载存档索引：package_id={package_id}")
    target_view = PackageView(package_index, resource_manager)
    validator = ComprehensiveValidator(target_view, resource_manager, verbose=False)
    issues = validator.validate_all()

    error_issues = [issue for issue in issues if issue.level == "error"]
    warning_issues = [issue for issue in issues if issue.level == "warning"]

    def normalize_issue(issue: Any) -> Dict[str, Any]:
        return {
            "level": getattr(issue, "level", ""),
            "category": getattr(issue, "category", ""),
            "location": getattr(issue, "location", ""),
            "message": getattr(issue, "message", ""),
        }

    return {
        "package_id": package_id,
        "errors": len(error_issues),
        "warnings": len(warning_issues),
        "error_samples": [normalize_issue(issue) for issue in error_issues[:20]],
        "warning_samples": [normalize_issue(issue) for issue in warning_issues[:20]],
    }


def find_graph_generater_root_from_output_package_root(output_package_root: Path) -> Path | None:
    """对外 API：从项目存档目录推断 Graph_Generater 根目录（找不到则返回 None）。"""
    return _find_graph_generater_root_from_output_package_root(Path(output_package_root).resolve())


def validate_graph_generater_single_package(*, graph_generater_root: Path, package_id: str) -> Dict[str, Any]:
    """对外 API：用 Graph_Generater 引擎做单包综合校验（返回 errors/warnings 摘要）。"""
    return _validate_graph_generater_single_package(Path(graph_generater_root).resolve(), str(package_id))


