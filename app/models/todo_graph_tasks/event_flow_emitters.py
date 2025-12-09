"""事件流 Todo 的写操作，集中封装所有 TodoItem 创建逻辑"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from app.models import TodoItem
from app.models.todo_builder_helpers import (
    build_connect_todo_merged,
    build_connect_todo_single,
    build_create_node_todo,
)
from app.models.todo_graph_tasks.dynamic_port_steps import DynamicPortStepPlanner
from app.models.todo_pipeline.step_mode import GraphStepMode
from app.models.todo_structure_helpers import ensure_child_reference
from engine.graph.models import GraphModel
from engine.configs.settings import settings
from engine.graph.common import STRUCT_NODE_TITLES


class EventFlowEmitters:
    def __init__(
        self,
        *,
        add_todo: Callable[[TodoItem], None],
        dynamic_steps: DynamicPortStepPlanner,
    ) -> None:
        self._add_todo = add_todo
        self.dynamic_steps = dynamic_steps
        self._signal_param_types_by_node: Dict[str, Dict[str, Any]] = {}

    def set_signal_param_types(self, mapping: Dict[str, Dict[str, Any]]) -> None:
        """注册当前图中信号节点的参数类型映射，供信号绑定步骤使用。"""
        self._signal_param_types_by_node = dict(mapping or {})

    def clear_signal_param_types(self) -> None:
        """清除信号参数类型上下文。"""
        self._signal_param_types_by_node = {}

    def create_flow_root(
        self,
        *,
        graph_root: TodoItem,
        graph_root_id: str,
        graph_id: str,
        start_node_id: str,
        start_node_title: str,
        template_ctx_id: str,
        instance_ctx_id: str,
        suppress_auto_jump: bool,
        preview_template_id: str,
        task_type: str,
    ) -> TodoItem:
        flow_root_id = f"{graph_root_id}:flow:{start_node_id}"
        flow_detail = {
            "type": "event_flow_root",
            "graph_id": graph_id,
            "event_node_id": start_node_id,
            "event_node_title": start_node_title,
            "template_id": template_ctx_id if template_ctx_id else None,
            "instance_id": instance_ctx_id if instance_ctx_id else None,
            "graph_root_todo_id": graph_root_id,
            "task_type": task_type,
        }
        if suppress_auto_jump:
            flow_detail["no_auto_jump"] = True
        if preview_template_id:
            flow_detail["template_id"] = preview_template_id
        mode = GraphStepMode.current()
        flow_root = TodoItem(
            todo_id=flow_root_id,
            title=f"事件流：{start_node_title}",
            description=mode.flow_description(),
            level=4,
            parent_id=graph_root_id,
            children=[],
            task_type=task_type,
            target_id=graph_id,
            detail_info=flow_detail,
        )
        self._add_todo(flow_root)
        ensure_child_reference(graph_root, flow_root_id)
        return flow_root

    def create_event_start_step(
        self,
        *,
        flow_root: TodoItem,
        flow_root_id: str,
        graph_id: str,
        start_node,
        template_ctx_id: str,
        instance_ctx_id: str,
        suppress_auto_jump: bool,
        task_type: str,
    ) -> None:
        step_id = f"{flow_root_id}:create_event"
        event_step = build_create_node_todo(
            todo_id=step_id,
            parent_id=flow_root_id,
            graph_id=graph_id,
            node_id=start_node.id,
            node_title=start_node.title,
            template_ctx_id=template_ctx_id,
            instance_ctx_id=instance_ctx_id,
            suppress_auto_jump=suppress_auto_jump,
            task_type=task_type,
            title_override=f"创建事件节点：{start_node.title}",
            description_override="创建事件节点",
        )
        self._add_todo(event_step)
        ensure_child_reference(flow_root, step_id)

    def create_human_connection_step(
        self,
        *,
        flow_root: TodoItem,
        flow_root_id: str,
        graph_id: str,
        prev_node,
        next_node,
        edge,
        template_ctx_id: str,
        instance_ctx_id: str,
        suppress_auto_jump: bool,
        task_type: str,
    ) -> str:
        step_id = f"{flow_root_id}:edge:{edge.id}"
        connection_step = TodoItem(
            todo_id=step_id,
            title=f"连线并创建：{next_node.title}",
            description="从前一节点拖线创建并连接",
            level=5,
            parent_id=flow_root_id,
            children=[],
            task_type=task_type,
            target_id=graph_id,
            detail_info={
                "type": "graph_create_and_connect",
                "graph_id": graph_id,
                "prev_node_id": prev_node.id,
                "prev_node_title": prev_node.title,
                "node_id": next_node.id,
                "node_title": next_node.title,
                "edge_id": edge.id,
                "template_id": template_ctx_id if template_ctx_id else None,
                "instance_id": instance_ctx_id if instance_ctx_id else None,
                "no_auto_jump": suppress_auto_jump,
            },
        )
        self._add_todo(connection_step)
        ensure_child_reference(flow_root, step_id)
        return step_id

    def create_data_node_step(
        self,
        *,
        flow_root: TodoItem,
        flow_root_id: str,
        current_node,
        data_node,
        edge,
        model: GraphModel,
        graph_id: str,
        template_ctx_id: str,
        instance_ctx_id: str,
        suppress_auto_jump: bool,
        task_type: str,
    ) -> None:
        is_copy = getattr(data_node, "is_data_node_copy", False)
        original_id = getattr(data_node, "original_node_id", "") if is_copy else ""
        data_step_id = f"{flow_root_id}:data:{data_node.id}"
        data_step = TodoItem(
            todo_id=data_step_id,
            title=f"连线并创建：{data_node.title}{'（副本）' if is_copy else ''}",
            description=(
                f"从{current_node.title}的输入端口反向拖线创建数据节点"
                + (f"（这是节点{original_id}的副本，因跨块共享而复制）" if is_copy else "")
            ),
            level=5,
            parent_id=flow_root_id,
            children=[],
            task_type=task_type,
            target_id=graph_id,
            detail_info={
                "type": "graph_create_and_connect_data",
                "graph_id": graph_id,
                "target_node_id": current_node.id,
                "target_node_title": current_node.title,
                "data_node_id": data_node.id,
                "data_node_title": data_node.title,
                "edge_id": edge.id,
                "is_copy": is_copy,
                "original_node_id": original_id if is_copy else None,
                "template_id": template_ctx_id if template_ctx_id else None,
                "instance_id": instance_ctx_id if instance_ctx_id else None,
                "no_auto_jump": suppress_auto_jump,
            },
        )
        self._add_todo(data_step)
        ensure_child_reference(flow_root, data_step_id)

        self.dynamic_steps.attach_dynamic_steps(
            flow_root=flow_root,
            flow_root_id=flow_root_id,
            graph_id=graph_id,
            node_obj=data_node,
            template_ctx_id=template_ctx_id,
            instance_ctx_id=instance_ctx_id,
            suppress_auto_jump=suppress_auto_jump,
            allow_branch_outputs=False,
            task_type=task_type,
        )
        params_payload = self.dynamic_steps.collect_constant_params(data_node)
        self.dynamic_steps.ensure_type_step(
            node_obj=data_node,
            flow_root=flow_root,
            flow_root_id=flow_root_id,
            graph_id=graph_id,
            template_ctx_id=template_ctx_id,
            instance_ctx_id=instance_ctx_id,
            suppress_auto_jump=suppress_auto_jump,
            task_type=task_type,
            step_id=f"{data_step_id}:types",
            params_payload=params_payload if params_payload else None,
        )
        self.dynamic_steps.ensure_param_step(
            node_obj=data_node,
            flow_root=flow_root,
            flow_root_id=flow_root_id,
            graph_id=graph_id,
            template_ctx_id=template_ctx_id,
            instance_ctx_id=instance_ctx_id,
            suppress_auto_jump=suppress_auto_jump,
            task_type=task_type,
            step_id=f"{data_step_id}:params",
            params_payload=params_payload if params_payload else None,
        )
        node_title = getattr(data_node, "title", "") or ""
        if node_title in STRUCT_NODE_TITLES:
            self.ensure_struct_binding_for_node(
                flow_root=flow_root,
                flow_root_id=flow_root_id,
                graph_id=graph_id,
                node_obj=data_node,
                template_ctx_id=template_ctx_id,
                instance_ctx_id=instance_ctx_id,
                suppress_auto_jump=suppress_auto_jump,
                task_type=task_type,
                model=model,
            )

    def create_node_batch(
        self,
        *,
        node_ids: List[str],
        flow_root: TodoItem,
        flow_root_id: str,
        model: GraphModel,
        created_nodes: set[str],
        graph_id: str,
        template_ctx_id: str,
        instance_ctx_id: str,
        suppress_auto_jump: bool,
        task_type: str,
    ) -> List[str]:
        processed_node_ids: List[str] = []
        params_payload_by_node: Dict[str, List[Dict[str, Any]]] = {}
        branch_steps_by_node: Dict[str, List[TodoItem]] = {}

        for node_id in node_ids:
            node_obj = model.nodes.get(node_id)
            if not node_obj:
                continue
            create_step_id = f"{flow_root_id}:create:{node_id}"
            create_step = build_create_node_todo(
                todo_id=create_step_id,
                parent_id=flow_root_id,
                graph_id=graph_id,
                node_id=node_id,
                node_title=node_obj.title,
                template_ctx_id=template_ctx_id,
                instance_ctx_id=instance_ctx_id,
                suppress_auto_jump=suppress_auto_jump,
                task_type=task_type,
            )
            self._add_todo(create_step)
            ensure_child_reference(flow_root, create_step_id)
            from engine.graph.common import SIGNAL_SEND_NODE_TITLE, SIGNAL_LISTEN_NODE_TITLE

            node_title = getattr(node_obj, "title", "") or ""
            if node_title in (SIGNAL_SEND_NODE_TITLE, SIGNAL_LISTEN_NODE_TITLE):
                self._ensure_signal_binding_todo(
                    flow_root=flow_root,
                    flow_root_id=flow_root_id,
                    graph_id=graph_id,
                    node_obj=node_obj,
                    template_ctx_id=template_ctx_id,
                    instance_ctx_id=instance_ctx_id,
                    suppress_auto_jump=suppress_auto_jump,
                    task_type=task_type,
                    model=model,
                )
            if node_title in STRUCT_NODE_TITLES:
                self.ensure_struct_binding_for_node(
                    flow_root=flow_root,
                    flow_root_id=flow_root_id,
                    graph_id=graph_id,
                    node_obj=node_obj,
                    template_ctx_id=template_ctx_id,
                    instance_ctx_id=instance_ctx_id,
                    suppress_auto_jump=suppress_auto_jump,
                    task_type=task_type,
                    model=model,
                )
            created_nodes.add(node_id)
            processed_node_ids.append(node_id)
            params_payload_by_node[node_id] = self.dynamic_steps.collect_constant_params(node_obj)
            if self.dynamic_steps.is_branching_node(node_obj):
                deferred_steps = self.dynamic_steps.attach_dynamic_steps(
                    flow_root=flow_root,
                    flow_root_id=flow_root_id,
                    graph_id=graph_id,
                    node_obj=node_obj,
                    template_ctx_id=template_ctx_id,
                    instance_ctx_id=instance_ctx_id,
                    suppress_auto_jump=suppress_auto_jump,
                    allow_branch_outputs=True,
                    defer_branch_steps=True,
                    task_type=task_type,
                )
                if deferred_steps:
                    branch_steps_by_node[node_id] = deferred_steps
            else:
                self.dynamic_steps.attach_dynamic_steps(
                    flow_root=flow_root,
                    flow_root_id=flow_root_id,
                    graph_id=graph_id,
                    node_obj=node_obj,
                    template_ctx_id=template_ctx_id,
                    instance_ctx_id=instance_ctx_id,
                    suppress_auto_jump=suppress_auto_jump,
                    allow_branch_outputs=False,
                    task_type=task_type,
                )

        for node_id in processed_node_ids:
            node_obj = model.nodes.get(node_id)
            if not node_obj:
                continue
            self.dynamic_steps.ensure_type_step(
                node_obj=node_obj,
                flow_root=flow_root,
                flow_root_id=flow_root_id,
                graph_id=graph_id,
                template_ctx_id=template_ctx_id,
                instance_ctx_id=instance_ctx_id,
                suppress_auto_jump=suppress_auto_jump,
                step_id=f"{flow_root_id}:create:{node_id}:types",
                params_payload=params_payload_by_node.get(node_id),
                task_type=task_type,
            )
            deferred_steps = branch_steps_by_node.pop(node_id, None)
            if deferred_steps:
                for todo in deferred_steps:
                    self._add_todo(todo)
                    ensure_child_reference(flow_root, todo.todo_id)

        for node_id in processed_node_ids:
            node_obj = model.nodes.get(node_id)
            if not node_obj:
                continue
            self.dynamic_steps.ensure_param_step(
                node_obj=node_obj,
                flow_root=flow_root,
                flow_root_id=flow_root_id,
                graph_id=graph_id,
                template_ctx_id=template_ctx_id,
                instance_ctx_id=instance_ctx_id,
                suppress_auto_jump=suppress_auto_jump,
                step_id=f"{flow_root_id}:create:{node_id}:params",
                params_payload=params_payload_by_node.get(node_id),
                task_type=task_type,
            )

        return processed_node_ids

    def handle_leftover_nodes(
        self,
        *,
        flow_root: TodoItem,
        flow_root_id: str,
        leftovers: List[str],
        model: GraphModel,
        created_nodes: set[str],
        graph_id: str,
        template_ctx_id: str,
        instance_ctx_id: str,
        suppress_auto_jump: bool,
        node_pos_key: Callable[[str], tuple],
        task_type: str,
    ) -> List[str]:
        leftovers_sorted = sorted(leftovers, key=node_pos_key)
        return self.create_node_batch(
            node_ids=leftovers_sorted,
            flow_root=flow_root,
            flow_root_id=flow_root_id,
            model=model,
            created_nodes=created_nodes,
            graph_id=graph_id,
            template_ctx_id=template_ctx_id,
            instance_ctx_id=instance_ctx_id,
            suppress_auto_jump=suppress_auto_jump,
            task_type=task_type,
        )

    def handle_remaining_edges(
        self,
        *,
        flow_root: TodoItem,
        flow_root_id: str,
        remaining_edges: Sequence,
        model: GraphModel,
        connected_edge_ids: set[str],
        graph_id: str,
        template_ctx_id: str,
        instance_ctx_id: str,
        suppress_auto_jump: bool,
        task_type: str,
    ) -> None:
        self.build_connection_steps(
            flow_root=flow_root,
            flow_root_id=flow_root_id,
            edges_to_connect=remaining_edges,
            model=model,
            connected_edge_ids=connected_edge_ids,
            graph_id=graph_id,
            template_ctx_id=template_ctx_id,
            instance_ctx_id=instance_ctx_id,
            suppress_auto_jump=suppress_auto_jump,
            task_type=task_type,
        )

    def build_connection_steps(
        self,
        *,
        flow_root: TodoItem,
        flow_root_id: str,
        edges_to_connect: Sequence,
        model: GraphModel,
        connected_edge_ids: set[str],
        graph_id: str,
        template_ctx_id: str,
        instance_ctx_id: str,
        suppress_auto_jump: bool,
        task_type: str,
    ) -> None:
        if not edges_to_connect:
            return
        if settings.TODO_MERGE_CONNECTION_STEPS:
            pair_to_edges: Dict[tuple[str, str], List] = {}
            for edge in edges_to_connect:
                key = (edge.src_node, edge.dst_node)
                pair_to_edges.setdefault(key, []).append(edge)
            for (src_node_id, dst_node_id), grouped in pair_to_edges.items():
                src_node = model.nodes.get(src_node_id)
                dst_node = model.nodes.get(dst_node_id)
                if not src_node or not dst_node:
                    continue
                edges_info = [
                    {"edge_id": grouped_edge.id, "src_port": grouped_edge.src_port, "dst_port": grouped_edge.dst_port}
                    for grouped_edge in grouped
                    if grouped_edge.id not in connected_edge_ids
                ]
                if not edges_info:
                    continue
                connect_id = f"{flow_root_id}:connect:{src_node_id}:{dst_node_id}"
                connect_step = build_connect_todo_merged(
                    todo_id=connect_id,
                    parent_id=flow_root_id,
                    graph_id=graph_id,
                    src_id=src_node_id,
                    dst_id=dst_node_id,
                    src_title=src_node.title,
                    dst_title=dst_node.title,
                    edges_info=edges_info,
                    template_ctx_id=template_ctx_id,
                    instance_ctx_id=instance_ctx_id,
                    suppress_auto_jump=suppress_auto_jump,
                    task_type=task_type,
                )
                self._add_todo(connect_step)
                ensure_child_reference(flow_root, connect_id)
                for grouped_edge in grouped:
                    connected_edge_ids.add(grouped_edge.id)
        else:
            for edge in edges_to_connect:
                if edge.id in connected_edge_ids:
                    continue
                src_node = model.nodes.get(edge.src_node)
                dst_node = model.nodes.get(edge.dst_node)
                if not src_node or not dst_node:
                    continue
                connect_id = f"{flow_root_id}:connect:{edge.id}"
                connect_step = build_connect_todo_single(
                    todo_id=connect_id,
                    parent_id=flow_root_id,
                    graph_id=graph_id,
                    edge=edge,
                    src_node_title=src_node.title,
                    dst_node_title=dst_node.title,
                    template_ctx_id=template_ctx_id,
                    instance_ctx_id=instance_ctx_id,
                    suppress_auto_jump=suppress_auto_jump,
                    task_type=task_type,
                )
                self._add_todo(connect_step)
                ensure_child_reference(flow_root, connect_id)
                connected_edge_ids.add(edge.id)

    def _ensure_signal_binding_todo(
        self,
        *,
        flow_root: TodoItem,
        flow_root_id: str,
        graph_id: str,
        node_obj,
        template_ctx_id: str,
        instance_ctx_id: str,
        suppress_auto_jump: bool,
        task_type: str,
        model: GraphModel,
    ) -> None:
        node_id = getattr(node_obj, "id", "") or ""
        if not node_id:
            return
        todo_id = f"{flow_root_id}:bind_signal:{node_id}"
        existing_map: Dict[str, TodoItem] = getattr(self.dynamic_steps, "todo_map", {})
        if todo_id in existing_map:
            return

        signal_param_names: List[str] = []
        if self._signal_param_types_by_node:
            type_map_for_node = self._signal_param_types_by_node.get(str(node_id)) or {}
            if isinstance(type_map_for_node, dict):
                for name in type_map_for_node.keys():
                    name_str = str(name or "")
                    if name_str:
                        signal_param_names.append(name_str)
                signal_param_names = sorted(signal_param_names)

        signal_id = model.get_node_signal_id(node_id) or ""
        input_constants = getattr(node_obj, "input_constants", {}) or {}
        signal_name = ""
        if isinstance(input_constants, dict):
            from engine.graph.common import SIGNAL_NAME_PORT_NAME

            if SIGNAL_NAME_PORT_NAME in input_constants:
                signal_name = str(input_constants.get(SIGNAL_NAME_PORT_NAME) or "")

        node_title = getattr(node_obj, "title", "") or ""
        if node_title == "监听信号":
            title = f"为事件节点【{node_title}】选择信号名"
        else:
            title = f"为【{node_title}】节点选择要发送的信号"

        detail_info: Dict[str, Any] = {
            "type": "graph_bind_signal",
            "graph_id": graph_id,
            "node_id": node_id,
            "node_title": node_title,
            "signal_id": signal_id or None,
            "signal_name": signal_name,
            "template_id": template_ctx_id if template_ctx_id else None,
            "instance_id": instance_ctx_id if instance_ctx_id else None,
        }
        if signal_param_names:
            detail_info["signal_param_names"] = signal_param_names
        if suppress_auto_jump:
            detail_info["no_auto_jump"] = True

        todo = TodoItem(
            todo_id=todo_id,
            title=title,
            description="在节点上选择或确认绑定的信号定义",
            level=5,
            parent_id=flow_root_id,
            children=[],
            task_type=task_type,
            target_id=graph_id,
            detail_info=detail_info,
        )
        self._add_todo(todo)
        ensure_child_reference(flow_root, todo_id)

    def _ensure_struct_binding_todo(
        self,
        *,
        flow_root: TodoItem,
        flow_root_id: str,
        graph_id: str,
        node_obj,
        template_ctx_id: str,
        instance_ctx_id: str,
        suppress_auto_jump: bool,
        task_type: str,
        model: GraphModel,
    ) -> None:
        node_id = getattr(node_obj, "id", "") or ""
        if not node_id:
            return
        node_title = getattr(node_obj, "title", "") or ""
        if node_title not in STRUCT_NODE_TITLES:
            return

        todo_id = f"{flow_root_id}:bind_struct:{node_id}"
        existing_map: Dict[str, TodoItem] = getattr(self.dynamic_steps, "todo_map", {})
        if todo_id in existing_map:
            return

        binding = model.get_node_struct_binding(node_id)
        struct_id_text = ""
        struct_name_text = ""
        field_names_list: List[str] = []
        if isinstance(binding, dict):
            raw_struct_id = binding.get("struct_id")
            if isinstance(raw_struct_id, str):
                struct_id_text = raw_struct_id.strip()
            elif raw_struct_id is not None:
                struct_id_text = str(raw_struct_id)

            raw_struct_name = binding.get("struct_name")
            if isinstance(raw_struct_name, str):
                struct_name_text = raw_struct_name.strip()

            raw_field_names = binding.get("field_names") or []
            if isinstance(raw_field_names, Sequence) and not isinstance(raw_field_names, (str, bytes)):
                for entry in raw_field_names:
                    if isinstance(entry, str) and entry:
                        field_names_list.append(entry)

        title = f"为【{node_title}】节点配置结构体"

        detail_info: Dict[str, Any] = {
            "type": "graph_bind_struct",
            "graph_id": graph_id,
            "node_id": node_id,
            "node_title": node_title,
            "struct_id": struct_id_text or None,
            "struct_name": struct_name_text,
            "field_names": field_names_list,
            "template_id": template_ctx_id if template_ctx_id else None,
            "instance_id": instance_ctx_id if instance_ctx_id else None,
        }
        if suppress_auto_jump:
            detail_info["no_auto_jump"] = True

        todo = TodoItem(
            todo_id=todo_id,
            title=title,
            description="在节点上选择或确认绑定的结构体与字段",
            level=5,
            parent_id=flow_root_id,
            children=[],
            task_type=task_type,
            target_id=graph_id,
            detail_info=detail_info,
        )
        self._add_todo(todo)
        ensure_child_reference(flow_root, todo_id)

    def ensure_signal_binding_for_event_start(
        self,
        *,
        flow_root: TodoItem,
        flow_root_id: str,
        graph_id: str,
        start_node,
        template_ctx_id: str,
        instance_ctx_id: str,
        suppress_auto_jump: bool,
        task_type: str,
        model: GraphModel,
    ) -> None:
        """为事件起点节点补充信号绑定步骤（主要用于“监听信号”事件节点）。"""
        self._ensure_signal_binding_todo(
            flow_root=flow_root,
            flow_root_id=flow_root_id,
            graph_id=graph_id,
            node_obj=start_node,
            template_ctx_id=template_ctx_id,
            instance_ctx_id=instance_ctx_id,
            suppress_auto_jump=suppress_auto_jump,
            task_type=task_type,
            model=model,
        )

    def ensure_struct_binding_for_node(
        self,
        *,
        flow_root: TodoItem,
        flow_root_id: str,
        graph_id: str,
        node_obj,
        template_ctx_id: str,
        instance_ctx_id: str,
        suppress_auto_jump: bool,
        task_type: str,
        model: GraphModel,
    ) -> None:
        """为任意结构体节点补充“配置结构体”步骤。"""
        self._ensure_struct_binding_todo(
            flow_root=flow_root,
            flow_root_id=flow_root_id,
            graph_id=graph_id,
            node_obj=node_obj,
            template_ctx_id=template_ctx_id,
            instance_ctx_id=instance_ctx_id,
            suppress_auto_jump=suppress_auto_jump,
            task_type=task_type,
            model=model,
        )

