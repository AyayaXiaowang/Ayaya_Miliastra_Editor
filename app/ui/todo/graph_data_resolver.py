from __future__ import annotations

from typing import Any, Optional

from app.common.graph_data_cache import resolve_graph_data
from app.models import TodoItem


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
    2. 否则通过 TodoPreviewController 解析 graph_data / graph_id 并按需加载；
    3. 若依然失败，优先使用 TreeManager.load_graph_data_for_root 按根 Todo 加载；
    4. 最后仅从 detail_info 的缓存 key 中解析（不再直接按 graph_id 触发资源加载）。
    """
    expected_graph_id = _resolve_expected_graph_id(focus_todo, root_todo)

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
    if (
        preview_panel is not None
        and hasattr(preview_panel, "preview_controller")
        and preview_panel.preview_controller is not None
    ):
        todo_map = getattr(tree_manager, "todo_map", {}) if tree_manager is not None else {}
        resolved_tuple = preview_panel.preview_controller.get_graph_data_id_and_container(
            focus_todo,
            todo_map,
            main_window,
            tree_manager,
        )
        if isinstance(resolved_tuple, tuple) and resolved_tuple:
            preview_graph_data = resolved_tuple[0]
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
        cached = resolve_graph_data(info)
        if _has_graph_structure(cached):
            return cached

    return None


