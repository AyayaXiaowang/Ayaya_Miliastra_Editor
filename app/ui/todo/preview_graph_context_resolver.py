from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from app.common.in_memory_graph_payload_cache import resolve_graph_data
from app.models import TodoItem
from engine.configs.settings import settings
from app.ui.todo.todo_config import StepTypeRules
from app.runtime.services.graph_data_service import get_shared_graph_data_service


def resolve_graph_preview_context(
    todo: Optional[TodoItem],
    todo_map: Dict[str, TodoItem],
    *,
    tree_manager: Any = None,
    main_window: Any = None,
) -> Tuple[Optional[dict], Optional[str], Optional[object]]:
    """解析给定 Todo 所属图的 graph_data / graph_id 以及预览容器对象。

    设计目标：
    - 预览与执行共用同一套“从 Todo 推导图上下文”的规则，避免多个入口各自实现一套优先级。
    - 图数据加载优先走 TreeManager/TodoTreeGraphSupport（其内部负责缓存与 ResourceManager 接入），
      本模块不直接按 graph_id 触发资源加载。
    """
    if todo is None:
        return (None, None, None)

    graph_id: Optional[str] = None
    graph_data: Optional[dict] = None

    root_todo_for_tree: Optional[TodoItem] = None
    detail_type = (todo.detail_info or {}).get("type", "")
    if tree_manager is not None:
        if StepTypeRules.is_graph_root(detail_type):
            root_todo_for_tree = todo
        else:
            find_root = getattr(tree_manager, "find_template_graph_root_for_todo", None)
            if callable(find_root):
                root_todo_for_tree = find_root(todo.todo_id)

        if root_todo_for_tree is not None:
            root_info = root_todo_for_tree.detail_info or {}
            graph_id_candidate = root_info.get("graph_id")
            if isinstance(graph_id_candidate, str) and graph_id_candidate:
                graph_id = graph_id_candidate

            load_graph_data_for_root = getattr(tree_manager, "load_graph_data_for_root", None)
            if callable(load_graph_data_for_root):
                loaded = load_graph_data_for_root(root_todo_for_tree)
                if isinstance(loaded, dict) and ("nodes" in loaded or "edges" in loaded):
                    graph_data = loaded

    # 回退：从 detail_info 的 graph_data_key（或内存缓存 key）解析
    if graph_id is None:
        graph_id = _resolve_graph_id(todo, todo_map)
    if graph_data is None:
        graph_data = _resolve_graph_data(todo, todo_map, main_window=main_window)

    container_obj = _resolve_template_or_instance(todo, todo_map, main_window)
    return (graph_data, graph_id, container_obj)


def _resolve_graph_data(todo: TodoItem, todo_map: Dict[str, TodoItem], *, main_window: Any) -> Optional[dict]:
    graph_data_service = None
    if main_window is not None:
        resource_manager = getattr(main_window, "resource_manager", None)
        package_index_manager = getattr(main_window, "package_index_manager", None)
        graph_data_service = get_shared_graph_data_service(resource_manager, package_index_manager)

    # 当前任务
    current_info = todo.detail_info or {}
    data = (
        graph_data_service.resolve_payload_graph_data(current_info)
        if graph_data_service is not None
        else resolve_graph_data(current_info)
    )
    if isinstance(data, dict) and ("nodes" in data or "edges" in data):
        if settings.PREVIEW_VERBOSE:
            print("[PREVIEW] graph_data 来自当前任务(detail_info)")
        return data

    # 向上查找：仅在“模板图根”处尝试读取图数据
    current_id = todo.todo_id
    depth = 0
    while current_id and depth < 10:
        current = todo_map.get(current_id)
        if not current:
            break
        detail_type = (current.detail_info or {}).get("type")
        if StepTypeRules.is_template_graph_root(detail_type):
            info = current.detail_info or {}
            data = (
                graph_data_service.resolve_payload_graph_data(info)
                if graph_data_service is not None
                else resolve_graph_data(info)
            )
            if isinstance(data, dict) and ("nodes" in data or "edges" in data):
                if settings.PREVIEW_VERBOSE:
                    print(f"[PREVIEW] graph_data 来自父任务(模板图根): {detail_type}")
                return data
            return None
        current_id = current.parent_id
        depth += 1

    if settings.PREVIEW_VERBOSE:
        print("[PREVIEW] 未找到 graph_data")
    return None


def _resolve_graph_id(todo: TodoItem, todo_map: Dict[str, TodoItem]) -> Optional[str]:
    # 当前任务
    gid = (todo.detail_info or {}).get("graph_id")
    if isinstance(gid, str) and gid:
        if settings.PREVIEW_VERBOSE:
            print(f"[PREVIEW] graph_id 来自当前任务: {gid}")
        return gid

    # 向上查找
    current_id = todo.parent_id
    depth = 0
    while current_id and depth < 10:
        current = todo_map.get(current_id)
        if not current:
            break
        gid = (current.detail_info or {}).get("graph_id")
        if isinstance(gid, str) and gid:
            if settings.PREVIEW_VERBOSE:
                print(f"[PREVIEW] graph_id 来自父任务: {gid}")
            return gid
        current_id = current.parent_id
        depth += 1

    if settings.PREVIEW_VERBOSE:
        print("[PREVIEW] 未找到 graph_id")
    return None


def _resolve_template_or_instance(
    todo: TodoItem,
    todo_map: Dict[str, TodoItem],
    main_window: Any,
) -> Optional[object]:
    if not main_window or not hasattr(main_window, "package_controller"):
        if settings.PREVIEW_VERBOSE:
            print("[PREVIEW] 无 main_window.package_controller，预览上下文不可用")
        return None

    current_package = main_window.package_controller.current_package
    if not current_package:
        if settings.PREVIEW_VERBOSE:
            print("[PREVIEW] 当前没有加载存档，预览上下文不可用")
        return None

    # 当前任务
    detail = todo.detail_info or {}
    template_id = detail.get("template_id")
    instance_id = detail.get("instance_id")
    if (not template_id) and isinstance(detail.get("target_id"), str) and "template:" in detail.get("target_id", ""):
        template_id = str(detail["target_id"]).split("template:")[-1]
    if template_id:
        obj = current_package.get_template(template_id)
        if settings.PREVIEW_VERBOSE:
            print(f"[PREVIEW] 预览容器: template_id={template_id}, found={bool(obj)}")
        return obj
    if instance_id:
        obj = current_package.get_instance(instance_id)
        if settings.PREVIEW_VERBOSE:
            print(f"[PREVIEW] 预览容器: instance_id={instance_id}, found={bool(obj)}")
        return obj

    # 向上查找
    current_id = todo.parent_id
    depth = 0
    while current_id and depth < 10:
        current = todo_map.get(current_id)
        if not current:
            break
        detail = current.detail_info or {}
        template_id = detail.get("template_id")
        instance_id = detail.get("instance_id")
        if (not template_id) and isinstance(detail.get("target_id"), str) and "template:" in detail.get("target_id", ""):
            template_id = str(detail["target_id"]).split("template:")[-1]
        if template_id:
            obj = current_package.get_template(template_id)
            if settings.PREVIEW_VERBOSE:
                print(
                    f"[PREVIEW] 预览容器(父任务): template_id={template_id}, found={bool(obj)}"
                )
            return obj
        if instance_id:
            obj = current_package.get_instance(instance_id)
            if settings.PREVIEW_VERBOSE:
                print(
                    f"[PREVIEW] 预览容器(父任务): instance_id={instance_id}, found={bool(obj)}"
                )
            return obj
        current_id = current.parent_id
        depth += 1
    return None


