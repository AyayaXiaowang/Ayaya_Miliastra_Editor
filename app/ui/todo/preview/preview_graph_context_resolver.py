from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from app.models import TodoItem
from engine.configs.settings import settings
from app.ui.todo.misc.todo_config import StepTypeRules
from app.runtime.services.graph_data_service import GraphDataService


def resolve_graph_preview_context(
    todo: Optional[TodoItem],
    todo_map: Dict[str, TodoItem],
    *,
    tree_manager: Any = None,
    graph_data_service: GraphDataService,
    current_package: object | None,
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
            root_todo_for_tree = tree_manager.find_template_graph_root_for_todo(todo.todo_id)

        if root_todo_for_tree is not None:
            root_info = root_todo_for_tree.detail_info or {}
            graph_id_candidate = root_info.get("graph_id")
            if isinstance(graph_id_candidate, str) and graph_id_candidate:
                graph_id = graph_id_candidate

            # 重要：此处只允许读取“进程内 payload 缓存”（graph_data_key），禁止在 UI 线程同步触发磁盘加载。
            # 磁盘加载应由预览面板在后台线程完成（避免超大图导致进入任务清单/切换步骤时 UI 卡死）。
            loaded = graph_data_service.resolve_payload_graph_data(root_info)
            if isinstance(loaded, dict) and ("nodes" in loaded or "edges" in loaded):
                graph_data = loaded

    # 回退：从 detail_info 的 graph_data_key（或内存缓存 key）解析
    if graph_id is None:
        graph_id = _resolve_graph_id(todo, todo_map)
    if graph_data is None:
        graph_data = _resolve_graph_data(todo, todo_map, graph_data_service=graph_data_service)

    container_obj = _resolve_template_or_instance(todo, todo_map, current_package=current_package)
    return (graph_data, graph_id, container_obj)


def _resolve_graph_data(
    todo: TodoItem,
    todo_map: Dict[str, TodoItem],
    *,
    graph_data_service: GraphDataService,
) -> Optional[dict]:
    # 当前任务
    current_info = todo.detail_info or {}
    data = graph_data_service.resolve_payload_graph_data(current_info)
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
            data = graph_data_service.resolve_payload_graph_data(info)
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
    *,
    current_package: object | None,
) -> Optional[object]:
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


