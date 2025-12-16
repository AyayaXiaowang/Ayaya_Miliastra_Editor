from __future__ import annotations

from typing import Any, Callable, List, Optional

from app.models import TodoItem
from engine.nodes.port_name_rules import get_dynamic_port_type
from engine.nodes.port_type_system import is_flow_port_with_context


def handle_graph_create_node(controller: Any, todo: TodoItem, current_version: int) -> None:
    node_id = todo.detail_info.get("node_id")
    # 创建节点：仅高亮新节点，不灰显其他元素
    controller._highlight_single_node_and_focus(
        node_id=node_id,
        current_version=current_version,
        dim_unrelated=False,
        hide_overlay=True,
    )


def handle_graph_config_node(controller: Any, todo: TodoItem, current_version: int) -> None:
    detail = todo.detail_info
    node_id = detail.get("node_id")
    param_name = detail.get("param_name")

    def extra_highlighting(node_identifier: str) -> None:
        if param_name:
            controller.view.highlight_port(node_identifier, param_name, is_input=True)

    controller._highlight_single_node_and_focus(
        node_id=node_id,
        current_version=current_version,
        dim_unrelated=True,
        hide_overlay=True,
        extra_highlighting=extra_highlighting if param_name else None,
    )


def handle_graph_config_node_merged(controller: Any, todo: TodoItem, current_version: int) -> None:
    detail = todo.detail_info
    node_id = detail.get("node_id")
    params = detail.get("params", []) or []

    def extra_highlighting(node_identifier: str) -> None:
        for param_info in params:
            param_name = param_info.get("param_name")
            if param_name:
                controller.view.highlight_port(node_identifier, param_name, is_input=True)

    controller._highlight_single_node_and_focus(
        node_id=node_id,
        current_version=current_version,
        dim_unrelated=True,
        hide_overlay=True,
        extra_highlighting=extra_highlighting if params else None,
    )


def handle_graph_set_port_types_merged(controller: Any, todo: TodoItem, current_version: int) -> None:
    node_id = todo.detail_info.get("node_id")
    if not node_id:
        controller._hide_overlay()
        controller._finalize_updates()
        return

    controller.view.highlight_node(node_id)
    # 高亮需要设置类型的端口：仅高亮类型为“泛型家族”（泛型/泛型*）的数据端口
    scene = controller.view.scene()
    if scene and hasattr(scene, "model") and scene.model and node_id in scene.model.nodes:
        node_obj = scene.model.nodes.get(node_id)
        # 获取节点定义以判断端口声明类型
        node_def = None
        if hasattr(scene, "get_node_def") and callable(getattr(scene, "get_node_def")):
            node_def = scene.get_node_def(node_obj)  # 依赖 scene.node_library

        # 判定：是否为“泛型家族”类型名
        def _is_generic_type_name(type_name: object) -> bool:
            if not isinstance(type_name, str):
                return False
            type_name_stripped = type_name.strip()
            return bool(type_name_stripped == "泛型" or type_name_stripped.startswith("泛型"))

        # 安全获取端口声明类型（支持 0~99 等范围占位）
        def _get_declared_port_type(
            definition: object,
            port_name: str,
            is_input: bool,
        ) -> Optional[str]:
            if definition is None:
                return None
            types_dict = (
                getattr(definition, "input_types", {})
                if is_input
                else getattr(definition, "output_types", {})
            )
            dynamic_type = getattr(definition, "dynamic_port_type", "") or ""
            return get_dynamic_port_type(str(port_name), dict(types_dict), str(dynamic_type))

        # 输入侧：仅高亮声明为泛型家族的端口（排除流程端口）
        inputs = list(getattr(node_obj, "inputs", []) or [])
        for port in inputs:
            port_name = getattr(port, "name", None)
            if (
                isinstance(port_name, str)
                and port_name
                and (not is_flow_port_with_context(node_obj, port_name, False))
            ):
                declared = _get_declared_port_type(node_def, port_name, is_input=True)
                if _is_generic_type_name(declared):
                    controller.view.highlight_port(node_id, port_name, is_input=True)

        # 输出侧：仅高亮声明为泛型家族的端口（排除流程端口）
        outputs = list(getattr(node_obj, "outputs", []) or [])
        for port in outputs:
            port_name = getattr(port, "name", None)
            if (
                isinstance(port_name, str)
                and port_name
                and (not is_flow_port_with_context(node_obj, port_name, True))
            ):
                declared = _get_declared_port_type(node_def, port_name, is_input=False)
                if _is_generic_type_name(declared):
                    controller.view.highlight_port(node_id, port_name, is_input=False)

    controller._dim_unrelated([node_id], [])
    controller._hide_overlay()
    controller._finalize_updates()

    controller._schedule_focus(
        current_version,
        lambda use_animation, nid=node_id: controller.view.focus_on_node(
            nid,
            use_animation=use_animation,
        ),
    )


def handle_graph_create_and_connect(controller: Any, todo: TodoItem, current_version: int) -> None:
    detail = todo.detail_info
    prev_node_id = detail.get("prev_node_id")
    node_id = detail.get("node_id")
    src_port = detail.get("src_port")
    dst_port = detail.get("dst_port")
    edge_id_from_detail = detail.get("edge_id")

    if not (prev_node_id and node_id and controller.view.scene()):
        controller._finalize_updates()
        return

    edge_id = controller._maybe_resolve_edge_id_from_model(
        fallback_edge_id=edge_id_from_detail,
        src_node_id=prev_node_id,
        src_port=src_port,
        dst_node_id=node_id,
        dst_port=dst_port,
    )

    controller.view.highlight_nodes_and_edge(  # type: ignore[arg-type]
        prev_node_id,
        node_id,
        edge_id,
        src_port,
        dst_port,
    )
    focused_edge_ids: List[Optional[str]] = [edge_id] if edge_id else []
    focused_node_ids = [prev_node_id, node_id]
    controller._dim_unrelated(focused_node_ids, focused_edge_ids)
    controller._finalize_updates()

    controller._schedule_focus(
        current_version,
        lambda use_animation, pnid=prev_node_id, nid=node_id, eid=edge_id, s_port=src_port, d_port=dst_port: controller._overlay_and_focus(
            pnid,
            nid,
            eid,
            s_port,
            d_port,
            use_animation=use_animation,
        ),
    )


def handle_graph_create_and_connect_reverse(
    controller: Any,
    todo: TodoItem,
    current_version: int,
) -> None:
    detail = todo.detail_info
    successor_node_id = detail.get("successor_node_id")
    node_id = detail.get("node_id")
    node_port = detail.get("node_port")
    successor_port = detail.get("successor_port")
    edge_id_from_detail = detail.get("edge_id")

    if not (successor_node_id and node_id and controller.view.scene()):
        controller._finalize_updates()
        return

    edge_id = controller._maybe_resolve_edge_id_from_model(
        fallback_edge_id=edge_id_from_detail,
        src_node_id=node_id,
        src_port=node_port,
        dst_node_id=successor_node_id,
        dst_port=successor_port,
    )

    controller.view.highlight_nodes_and_edge(  # type: ignore[arg-type]
        node_id,
        successor_node_id,
        edge_id,
        node_port,
        successor_port,
    )
    focused_edge_ids: List[Optional[str]] = [edge_id] if edge_id else []
    focused_node_ids = [node_id, successor_node_id]
    controller._dim_unrelated(focused_node_ids, focused_edge_ids)
    controller._finalize_updates()

    controller._schedule_focus(
        current_version,
        lambda use_animation, snid=successor_node_id, nid=node_id, eid=edge_id, n_port=node_port, s_port=successor_port: controller._overlay_and_focus(
            snid,
            nid,
            eid,
            n_port,
            s_port,
            order="dst-src",
            use_animation=use_animation,
        ),
    )


def handle_graph_create_and_connect_data(
    controller: Any,
    todo: TodoItem,
    current_version: int,
) -> None:
    detail = todo.detail_info
    target_node_id = detail.get("target_node_id")
    data_node_id = detail.get("data_node_id")
    edge_identifier = detail.get("edge_id")

    if not (target_node_id and data_node_id and controller.view.scene()):
        controller._finalize_updates()
        return

    controller.view.highlight_nodes_and_edge(
        data_node_id,
        target_node_id,
        edge_identifier,
    )
    focused_edge_ids: List[Optional[str]] = (
        [edge_identifier] if edge_identifier else []
    )
    focused_node_ids = [data_node_id, target_node_id]
    controller._dim_unrelated(focused_node_ids, focused_edge_ids)
    controller._finalize_updates()

    controller._schedule_focus(
        current_version,
        lambda use_animation, data_id=data_node_id, target_id=target_node_id, edge_id_value=edge_identifier: controller._overlay_and_focus(
            data_id,
            target_id,
            edge_id_value,
            None,
            None,
            use_animation=use_animation,
        ),
    )


def handle_graph_create_branch_node(controller: Any, todo: TodoItem, current_version: int) -> None:
    detail = todo.detail_info
    branch_node_id = detail.get("branch_node_id")
    node_id = detail.get("node_id")
    branch_name = detail.get("branch_name")

    if not (branch_node_id and node_id and controller.view.scene()):
        controller._finalize_updates()
        return

    controller.view.highlight_node(branch_node_id)
    controller.view.highlight_node(node_id)

    edge_id: Optional[str] = None
    scene = controller.view.scene()
    if scene and hasattr(scene, "model") and scene.model:
        for candidate_edge_id, edge in scene.model.edges.items():
            if (
                edge.src_node == branch_node_id
                and edge.dst_node == node_id
                and edge.src_port == branch_name
            ):
                edge_id = candidate_edge_id
                break

    if edge_id:
        controller.view.highlight_edge(edge_id, is_flow_edge=True)

    focused_edge_ids: List[Optional[str]] = [edge_id] if edge_id else []
    focused_node_ids = [branch_node_id, node_id]
    controller._dim_unrelated(focused_node_ids, focused_edge_ids)
    controller._finalize_updates()

    controller._schedule_focus(
        current_version,
        lambda use_animation, b_id=branch_node_id, nid=node_id, eid=edge_id, b_port=branch_name: controller._overlay_and_focus(
            b_id,
            nid,
            eid,
            b_port,
            "流程入",
            use_animation=use_animation,
        ),
    )


def handle_graph_connect(controller: Any, todo: TodoItem, current_version: int) -> None:
    detail = todo.detail_info
    src_node_id = detail.get("src_node")
    dst_node_id = detail.get("dst_node")
    edge_id = detail.get("edge_id")
    src_port = detail.get("src_port")
    dst_port = detail.get("dst_port")

    if not (src_node_id and dst_node_id):
        controller._finalize_updates()
        return

    is_flow_edge = controller._is_flow_edge_between(
        src_node_id, src_port, dst_node_id, dst_port
    )
    controller.view.highlight_edge(edge_id, is_flow_edge=is_flow_edge)

    scene = controller.view.scene()
    if scene and edge_id and hasattr(scene, "edge_items") and edge_id in scene.edge_items:
        focused_edge_ids: List[Optional[str]] = [edge_id]
    else:
        focused_edge_ids = []
    focused_node_ids = [src_node_id, dst_node_id]
    controller._dim_unrelated(focused_node_ids, focused_edge_ids)
    controller._finalize_updates()

    controller._schedule_focus(
        current_version,
        lambda use_animation, s_node=src_node_id, d_node=dst_node_id, eid=edge_id, s_port=src_port, d_port=dst_port: controller._overlay_and_focus(
            s_node,
            d_node,
            eid,
            s_port,
            d_port,
            use_animation=use_animation,
        ),
    )


def handle_graph_connect_merged(controller: Any, todo: TodoItem, current_version: int) -> None:
    detail = todo.detail_info
    node1_id = detail.get("node1_id")
    node2_id = detail.get("node2_id")
    edges_info = detail.get("edges", []) or []

    if not (node1_id and node2_id and edges_info):
        controller._finalize_updates()
        return

    focused_edge_ids: List[str] = []
    for edge_info in edges_info:
        edge_id_in_group = edge_info.get("edge_id")
        src_port = edge_info.get("src_port")
        dst_port = edge_info.get("dst_port")
        if not edge_id_in_group:
            continue

        is_flow_edge = controller._is_flow_edge_between(
            node1_id, src_port, node2_id, dst_port
        )
        controller.view.highlight_edge(edge_id_in_group, is_flow_edge=is_flow_edge)
        focused_edge_ids.append(edge_id_in_group)

        if src_port:
            controller.view.highlight_port(node1_id, src_port, is_input=False)
        if dst_port:
            controller.view.highlight_port(node2_id, dst_port, is_input=True)

    controller._dim_unrelated([node1_id, node2_id], focused_edge_ids)
    controller._finalize_updates()

    def _merged_focus(use_animation: bool) -> None:
        if controller.view.overlay_manager and edges_info:
            first_src = edges_info[0].get("src_port")
            first_dst = edges_info[0].get("dst_port")
            controller.view.overlay_manager.show_node_pair(
                node1_id, node2_id, first_src, first_dst
            )
        first_edge_id = edges_info[0].get("edge_id") if edges_info else None
        controller.view.focus_on_nodes_and_edge(
            node1_id,
            node2_id,
            first_edge_id,
            use_animation=use_animation,
        )

    controller._schedule_focus(current_version, _merged_focus)


def handle_template_graph_root(controller: Any, todo: TodoItem, current_version: int) -> None:
    controller._hide_overlay()
    controller._finalize_updates()

    controller._schedule_focus(
        current_version,
        lambda use_animation: controller.view.fit_all(use_animation=use_animation),
    )


def handle_dynamic_port_step(controller: Any, todo: TodoItem, current_version: int) -> None:
    # 动态端口添加：高亮目标节点并聚焦（与创建/配置类体验一致）
    node_id = todo.detail_info.get("node_id")
    controller._highlight_single_node_and_focus(
        node_id=node_id,
        current_version=current_version,
        dim_unrelated=True,
        hide_overlay=True,
    )


def handle_graph_signals_overview(controller: Any, todo: TodoItem, current_version: int) -> None:
    # 高亮本图中所有使用信号的节点，并聚焦到这些节点所在区域
    signals = todo.detail_info.get("signals", []) or []
    node_ids: List[str] = []
    for signal_entry in signals:
        nodes_info = signal_entry.get("nodes") or []
        for node_info in nodes_info:
            node_id = node_info.get("node_id")
            if node_id and node_id not in node_ids:
                node_ids.append(node_id)

    if node_ids:
        for node_identifier in node_ids:
            controller.view.highlight_node(node_identifier)
        controller._dim_unrelated(node_ids, [])
        controller._hide_overlay()
        controller._finalize_updates()

        controller._schedule_focus(
            current_version,
            lambda use_animation, nids=list(node_ids): controller._focus_on_node_group(
                nids, use_animation=use_animation
            ),
        )
        return

    controller._hide_overlay()
    controller._finalize_updates()

    controller._schedule_focus(
        current_version,
        lambda use_animation: controller.view.fit_all(use_animation=use_animation),
    )


def handle_graph_bind_signal(controller: Any, todo: TodoItem, current_version: int) -> None:
    node_id = todo.detail_info.get("node_id")
    controller._highlight_single_node_and_focus(
        node_id=node_id,
        current_version=current_version,
        dim_unrelated=True,
        hide_overlay=True,
    )


def handle_graph_bind_struct(controller: Any, todo: TodoItem, current_version: int) -> None:
    node_id = todo.detail_info.get("node_id")
    controller._highlight_single_node_and_focus(
        node_id=node_id,
        current_version=current_version,
        dim_unrelated=True,
        hide_overlay=True,
    )


