from __future__ import annotations

"""
validate-graphs 的编排层（引擎侧可复用）。

职责定位：
- 组合 `engine.validate.validate_files(...)` 的基础校验结果；
- 按需叠加：复合节点结构校验（UI 同款“缺少数据来源/未连接”等）；

边界：
- 本模块只返回 `EngineIssue` 列表，不做任何输出；
- 不解析命令行参数，CLI/UI 负责收敛 targets 与输出格式；
- 作为“编排层”允许依赖 `engine.validate.*` 与 `engine.nodes.*` 的公共入口。
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from engine.validate.api import validate_files
from engine.validate.composite_structural_checks import collect_composite_structural_issues
from engine.validate.issue import EngineIssue

__all__ = [
    "ValidateGraphsOrchestrationOptions",
    "collect_validate_graphs_engine_issues",
]


@dataclass(frozen=True)
class ValidateGraphsOrchestrationOptions:
    strict_entity_wire_only: bool = False
    use_cache: bool = True
    enable_composite_struct_check: bool = True


def collect_validate_graphs_engine_issues(
    targets: Sequence[Path],
    workspace_root: Path,
    *,
    options: ValidateGraphsOrchestrationOptions,
) -> List[EngineIssue]:
    """统一产出 validate-graphs 的 EngineIssue 列表（供 app-cli/UI 复用）。"""

    def _infer_active_package_id_for_file(file_path: Path) -> str | None:
        """根据文件路径推断其所属项目存档作用域（None=共享根）。"""
        from engine.utils.resource_library_layout import (
            PROJECT_ARCHIVE_LIBRARY_DIRNAME,
            SHARED_LIBRARY_DIRNAME,
            find_containing_resource_root,
        )

        resource_library_root = (workspace_root / "assets" / "资源库").resolve()
        resolved_file = file_path.resolve()
        resource_root = find_containing_resource_root(resource_library_root, resolved_file)
        if resource_root is None:
            return None
        if resource_root.name == SHARED_LIBRARY_DIRNAME:
            return None
        if resource_root.parent.name == PROJECT_ARCHIVE_LIBRARY_DIRNAME:
            return resource_root.name
        return None

    def _apply_scope_and_refresh_node_library(active_package_id: str | None) -> None:
        """应用当前作用域（共享 / 共享+存档）并刷新节点库/Schema 缓存。

        注意：validate-graphs 可能一次校验多个项目存档的文件；必须按文件所属存档切换作用域，
        否则复合节点、结构体/信号/关卡变量等代码级定义会串包，导致误报或漏报。
        """
        from engine.utils.runtime_scope import set_active_package_id as set_runtime_active_package_id

        from engine.resources.definition_schema_view import (
            set_default_definition_schema_view_active_package_id,
        )
        from engine.resources.level_variable_schema_view import (
            set_default_level_variable_schema_view_active_package_id,
        )
        from engine.resources.ingame_save_template_schema_view import (
            set_default_ingame_save_template_schema_view_active_package_id,
        )
        from engine.signal import invalidate_default_signal_repository_cache
        from engine.struct import invalidate_default_struct_repository_cache

        set_runtime_active_package_id(active_package_id)
        set_default_definition_schema_view_active_package_id(active_package_id)
        set_default_level_variable_schema_view_active_package_id(active_package_id)
        set_default_ingame_save_template_schema_view_active_package_id(active_package_id)
        invalidate_default_signal_repository_cache()
        invalidate_default_struct_repository_cache()

        # NodeRegistry 需要显式 refresh 才会按新作用域重建复合节点集合。
        from engine.nodes.node_registry import get_node_registry

        registry = get_node_registry(workspace_root, include_composite=True)
        registry.refresh()

    # --- 1) 分组：按文件所属项目存档作用域分别执行 validate_files / composite_struct_check ---
    files = list(targets or [])
    grouped: Dict[str | None, List[Path]] = {}
    for file_path in files:
        group_key = _infer_active_package_id_for_file(file_path) if isinstance(file_path, Path) else None
        grouped.setdefault(group_key, []).append(file_path)

    # 稳定顺序：共享根在前，其余存档按名称排序，避免输出与缓存行为漂移。
    ordered_groups: List[Tuple[str | None, List[Path]]] = []
    if None in grouped:
        ordered_groups.append((None, grouped.pop(None)))
    for pkg_id in sorted(grouped.keys(), key=lambda x: str(x or "").casefold()):
        ordered_groups.append((pkg_id, grouped[pkg_id]))

    issues: List[EngineIssue] = []

    for active_package_id, group_targets in ordered_groups:
        _apply_scope_and_refresh_node_library(active_package_id)

        report = validate_files(
            list(group_targets or []),
            workspace_root,
            strict_entity_wire_only=bool(options.strict_entity_wire_only),
            use_cache=bool(options.use_cache),
        )
        issues.extend(list(report.issues))

        if bool(options.enable_composite_struct_check):
            issues.extend(collect_composite_structural_issues(group_targets, workspace_root))

    return issues


