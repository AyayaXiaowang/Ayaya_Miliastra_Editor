from __future__ import annotations

from typing import Any, Optional

from app.common.in_memory_graph_payload_cache import resolve_graph_data
from app.models import TodoItem
from app.ui.todo.preview_graph_context_resolver import resolve_graph_preview_context
from app.runtime.services.graph_data_service import get_shared_graph_data_service


def _has_graph_structure(data: object) -> bool:
    """判断给定对象是否看起来像图数据."""
    if not isinstance(data, dict):
        return False
    return ("nodes" in data) or ("edges" in data)


def _resolve_expected_graph_id(
    focus_todo: Optional[TodoItem],
    root_todo: Optional[TodoItem],
) -> str:
    """根据执行上下文解析期望的 graph_id（用于与预览状态对齐）。

    优先级：
    1. 根 Todo 的 graph_id（模板图根 / 事件流根）；
    2. 叶子步骤自身的 graph_id；
    3. 若均缺失，则返回空字符串。
    """
    if root_todo is not None and isinstance(root_todo.detail_info, dict):
        graph_identifier = root_todo.detail_info.get("graph_id")
        if isinstance(graph_identifier, str) and graph_identifier:
            return graph_identifier
    if focus_todo is not None and isinstance(focus_todo.detail_info, dict):
        graph_identifier = focus_todo.detail_info.get("graph_id")
        if isinstance(graph_identifier, str) and graph_identifier:
            return graph_identifier
    return ""


def resolve_graph_data_for_execution(
    focus_todo: Optional[TodoItem],
    root_todo: Optional[TodoItem],
    *,
    preview_panel: Any = None,
    tree_manager: Any = None,
    main_window: Any = None,
) -> Optional[dict]:
    """为执行场景解析 graph_data。

    加载顺序：
    1. 若预览面板当前图与执行上下文 graph_id 一致，则优先复用 `current_graph_data`；
    2. 否则通过 `preview_graph_context_resolver.resolve_graph_preview_context` 解析并按需加载；
    3. 若依然失败，优先使用 TreeManager.load_graph_data_for_root 按根 Todo 加载；
    4. 最后仅从 detail_info 的缓存 key 中解析（不再直接按 graph_id 触发资源加载）。
    """
    expected_graph_id = _resolve_expected_graph_id(focus_todo, root_todo)
    graph_data_service = None
    if main_window is not None:
        resource_manager = getattr(main_window, "resource_manager", None)
        package_index_manager = getattr(main_window, "package_index_manager", None)
        graph_data_service = get_shared_graph_data_service(resource_manager, package_index_manager)

    # 1) 仅在“预览当前图”与执行上下文一致时复用预览面板图数据
    if preview_panel is not None:
        current_preview_data = getattr(preview_panel, "current_graph_data", None)
        current_preview_graph_id = getattr(preview_panel, "current_graph_id", None)
        if _has_graph_structure(current_preview_data):
            if (not expected_graph_id) or (
                isinstance(current_preview_graph_id, str)
                and current_preview_graph_id == expected_graph_id
            ):
                return current_preview_data

    # 2) 通过 TodoPreviewController 统一解析（含 graph_id 兜底与缓存写回 & 图根加载逻辑）
    todo_map = getattr(tree_manager, "todo_map", {}) if tree_manager is not None else {}
    target_todo = focus_todo or root_todo
    if target_todo is not None:
        preview_graph_data, _graph_id, _container = resolve_graph_preview_context(
            target_todo,
            todo_map,
            tree_manager=tree_manager,
            main_window=main_window,
        )
        if _has_graph_structure(preview_graph_data):
            return preview_graph_data

    # 3) 通过 TreeManager/TodoTreeGraphSupport 的图根加载逻辑解析
    if tree_manager is not None and root_todo is not None and hasattr(
        tree_manager, "load_graph_data_for_root"
    ):
        loaded = tree_manager.load_graph_data_for_root(root_todo)
        if _has_graph_structure(loaded):
            return loaded

    # 4) 最后兜底：仅从 detail_info 的缓存 key 中解析（不再直接按 graph_id 触发资源加载）
    info_candidates = []
    if root_todo is not None:
        info_candidates.append(root_todo.detail_info or {})
    if focus_todo is not None and focus_todo is not root_todo:
        info_candidates.append(focus_todo.detail_info or {})

    for info in info_candidates:
        cached = (
            graph_data_service.resolve_payload_graph_data(info)
            if graph_data_service is not None
            else resolve_graph_data(info)
        )
        if _has_graph_structure(cached):
            return cached

    return None


