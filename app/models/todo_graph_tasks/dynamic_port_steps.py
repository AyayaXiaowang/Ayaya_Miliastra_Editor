"""事件流任务中的动态端口 / 参数步骤规划器"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from app.models import TodoItem
from app.models.todo_builder_helpers import (
    build_config_branch_outputs_todo,
    build_params_todo,
    build_set_port_types_todo,
    DynamicPortTodoPlan,
    maybe_build_dynamic_ports_todo,
)
from app.models.todo_graph_tasks.edge_lookup import GraphEdgeLookup
from app.models.todo_node_type_helper import NodeTypeHelper
from app.models.todo_structure_helpers import ensure_child_reference
from engine.graph.common import SIGNAL_SEND_NODE_TITLE, SIGNAL_LISTEN_NODE_TITLE


class DynamicPortStepPlanner:
    def __init__(
        self,
        *,
        type_helper: NodeTypeHelper,
        add_todo: Callable[[TodoItem], None],
        todo_map: Dict[str, TodoItem],
    ) -> None:
        self.type_helper = type_helper
        self._add_todo = add_todo
        self.todo_map = todo_map
        self._edge_lookup: Optional[GraphEdgeLookup] = None
        self._signal_param_types_by_node: Dict[str, Dict[str, Any]] = {}

    def set_graph_context(self, edge_lookup: GraphEdgeLookup) -> None:
        """在当前事件流范围内注册边索引视图。

        说明：
        - 仅在构建事件流 Todo 期间调用；
        - 用于在收集参数时判断某个输入端口是否已有数据连线。
        """
        self._edge_lookup = edge_lookup

    def clear_graph_context(self) -> None:
        """清除当前图上下文，避免在跨图时复用错误的边索引。"""
        self._edge_lookup = None

    def set_signal_param_types(self, mapping: Dict[str, Dict[str, Any]]) -> None:
        """注册当前图中信号节点的参数类型映射，用于在参数步骤中补充 expected_type。"""
        self._signal_param_types_by_node = dict(mapping or {})

    def clear_signal_param_types(self) -> None:
        """清除信号参数类型上下文。"""
        self._signal_param_types_by_node = {}

    def attach_dynamic_steps(
        self,
        *,
        flow_root: TodoItem,
        flow_root_id: str,
        graph_id: str,
        node_obj,
        template_ctx_id: str,
        instance_ctx_id: str,
        suppress_auto_jump: bool,
        allow_branch_outputs: bool = False,
        defer_branch_steps: bool = False,
        task_type: str,
    ) -> List[TodoItem]:
        deferred_steps: List[TodoItem] = []
        dynamic_plan: Optional[DynamicPortTodoPlan] = maybe_build_dynamic_ports_todo(
            parent_id=flow_root_id,
            graph_id=graph_id,
            node_obj=node_obj,
            template_ctx_id=template_ctx_id,
            instance_ctx_id=instance_ctx_id,
            suppress_auto_jump=suppress_auto_jump,
            todo_map=self.todo_map,
            type_helper=self.type_helper,
            task_type=task_type,
        )
        if dynamic_plan is None:
            return deferred_steps
        dynamic_todo = dynamic_plan.todo
        is_branch_behavior = dynamic_plan.plan.mode == "flow_branch_outputs"
        should_defer_branch = defer_branch_steps and is_branch_behavior
        if should_defer_branch:
            deferred_steps.append(dynamic_todo)
        else:
            self._add_todo(dynamic_todo)
            ensure_child_reference(flow_root, dynamic_todo.todo_id)
        if not allow_branch_outputs or not is_branch_behavior:
            return deferred_steps
        config_todo = build_config_branch_outputs_todo(
            parent_id=flow_root_id,
            graph_id=graph_id,
            node_obj=node_obj,
            template_ctx_id=template_ctx_id,
            instance_ctx_id=instance_ctx_id,
            suppress_auto_jump=suppress_auto_jump,
            todo_map=self.todo_map,
            task_type=task_type,
        )
        if config_todo is not None:
            if should_defer_branch:
                deferred_steps.append(config_todo)
            else:
                self._add_todo(config_todo)
                ensure_child_reference(flow_root, config_todo.todo_id)
        return deferred_steps

    def collect_constant_params(self, node_obj) -> List[Dict[str, Any]]:
        """从节点的输入常量中收集需要配置的参数。

        规则：
        - 基础来源是 node_obj.input_constants；
        - 若当前图上下文可用，则跳过那些已有“数据连线”的输入端口，避免对同一端口同时发出“连线 + 配置常量”的指令；
        - 按约定忽略一部分“默认已满足”的布尔常量（例如: 值为 True/true/是 的布尔输入），避免为默认值生成多余的配置步骤。
        """
        constants = getattr(node_obj, "input_constants", None)
        if not constants:
            return []

        if self._edge_lookup is None:
            payload: List[Dict[str, Any]] = []
            for constant_name, constant_value in constants.items():
                if self._should_skip_constant_param(constant_value):
                    continue
                payload.append({"param_name": constant_name, "param_value": constant_value})
            return payload

        result: List[Dict[str, Any]] = []
        node_id = getattr(node_obj, "id", "")
        for key, value in constants.items():
            port_name = str(key)
            if self._should_skip_constant_param(value):
                continue
            edges_for_input = self._edge_lookup.input_edges_map.get((node_id, port_name), [])
            has_data_edge = False
            if edges_for_input:
                for edge in edges_for_input:
                    if edge.id not in self._edge_lookup.flow_edge_ids:
                        has_data_edge = True
                        break
            if has_data_edge:
                continue
            result.append({"param_name": key, "param_value": value})
        return result

    def _should_skip_constant_param(self, param_value: Any) -> bool:
        """根据约定判断某个输入常量是否应当跳过参数配置步骤。

        当前规则：
        - 若常量值等同于布尔“真”（如 True/true/是，忽略英文大小写与首尾空白），
          视为“默认恒为真”的条件，不生成对应的配置参数步骤。
        """
        if isinstance(param_value, str):
            value_text = param_value.strip()
        else:
            value_text = str(param_value).strip()

        lower = value_text.lower()

        # 1) 跳过“默认恒为真”的布尔常量
        if lower == "true":
            return True
        if value_text == "是":
            return True

        # 2) 将文本常量 "None" 视为“未填写”，不生成参数配置步骤
        if lower == "none":
            return True

        return False

    def is_branching_node(self, node_obj) -> bool:
        behavior = self.type_helper.describe_dynamic_port_behavior(node_obj)
        return bool(behavior and behavior.mode == "flow_branch_outputs")

    def ensure_type_step(
        self,
        *,
        node_obj,
        flow_root: TodoItem,
        flow_root_id: str,
        graph_id: str,
        template_ctx_id: str,
        instance_ctx_id: str,
        suppress_auto_jump: bool,
        step_id: str,
        params_payload: Optional[List[Dict[str, Any]]] = None,
        force: bool = False,
        task_type: str,
    ) -> None:
        # 信号节点的端口类型完全由信号定义决定，不需要也不应该生成“设置类型”步骤。
        node_title = getattr(node_obj, "title", "") or ""
        if node_title in (SIGNAL_SEND_NODE_TITLE, SIGNAL_LISTEN_NODE_TITLE):
            return
        if step_id in self.todo_map:
            return
        if not force and not self.type_helper.has_generic_ports_for_node(node_obj):
            return

        # 仅围绕“需要显式设置类型的泛型端口”构建类型步骤 payload：
        # - 初始 payload 仅保留在 params_payload 中出现的泛型端口；
        # - 随后再补齐剩余未出现在 params_payload 中的泛型输入/输出端口。
        generic_inputs = self.type_helper.list_generic_input_ports(node_obj)
        generic_outputs = self.type_helper.list_generic_output_ports(node_obj)
        generic_names: set[str] = set(generic_inputs) | set(generic_outputs)

        payload: List[Dict[str, Any]] = []
        if params_payload:
            for entry in params_payload:
                name_raw = entry.get("param_name")
                name = str(name_raw) if name_raw is not None else ""
                if not name:
                    continue
                # 若能够解析出泛型端口集合，则只保留其中的端口，避免为非泛型端口生成多余的类型步骤。
                if generic_names and name not in generic_names:
                    continue
                payload.append(dict(entry))

        # 补充所有需要显式设置类型的端口：
        # 1) 泛型输入端口（用于选择具体类型）；
        # 2) 泛型输出端口（用于在步骤明细中呈现需要设置的输出类型）。
        existing_names: set[str] = set()
        for entry in payload:
            name_raw = entry.get("param_name")
            name = str(name_raw) if name_raw is not None else ""
            if name:
                existing_names.add(name)

        for name in generic_inputs:
            if name not in existing_names:
                payload.append({"param_name": name, "param_value": ""})
                existing_names.add(name)

        for name in generic_outputs:
            if name not in existing_names:
                payload.append({"param_name": name, "param_value": ""})
                existing_names.add(name)

        if not payload and not force:
            return
        types_todo = build_set_port_types_todo(
            todo_id=step_id,
            parent_id=flow_root_id,
            graph_id=graph_id,
            node_id=node_obj.id,
            node_title=node_obj.title,
            params=payload,
            template_ctx_id=template_ctx_id,
            instance_ctx_id=instance_ctx_id,
            suppress_auto_jump=suppress_auto_jump,
            task_type=task_type,
        )
        self._add_todo(types_todo)
        ensure_child_reference(flow_root, step_id)

    def ensure_param_step(
        self,
        *,
        node_obj,
        flow_root: TodoItem,
        flow_root_id: str,
        graph_id: str,
        template_ctx_id: str,
        instance_ctx_id: str,
        suppress_auto_jump: bool,
        step_id: str,
        params_payload: Optional[List[Dict[str, Any]]] = None,
        task_type: str,
    ) -> None:
        if step_id in self.todo_map:
            return
        payload = [dict(entry) for entry in params_payload] if params_payload else []
        if not payload:
            payload = self.collect_constant_params(node_obj)
        # 再次按约定过滤一遍，确保外部传入的 params_payload 也遵守跳过规则
        if payload:
            filtered_payload: List[Dict[str, Any]] = []
            for entry in payload:
                value_raw = entry.get("param_value")
                if self._should_skip_constant_param(value_raw):
                    continue
                filtered_payload.append(entry)
            payload = filtered_payload
        if not payload:
            return

        node_id = getattr(node_obj, "id", "")
        node_title = getattr(node_obj, "title", "") or ""
        from engine.graph.common import SIGNAL_SEND_NODE_TITLE

        if node_id and node_title == SIGNAL_SEND_NODE_TITLE and self._signal_param_types_by_node:
            type_map = self._signal_param_types_by_node.get(str(node_id)) or {}
            if type_map:
                for entry in payload:
                    name_raw = entry.get("param_name")
                    name = str(name_raw) if name_raw is not None else ""
                    if not name:
                        continue
                    expected = type_map.get(name)
                    if expected and "expected_type" not in entry:
                        entry["expected_type"] = expected

        params_todo = build_params_todo(
            todo_id=step_id,
            parent_id=flow_root_id,
            graph_id=graph_id,
            node_id=node_obj.id,
            node_title=node_obj.title,
            params=payload,
            template_ctx_id=template_ctx_id,
            instance_ctx_id=instance_ctx_id,
            suppress_auto_jump=suppress_auto_jump,
            task_type=task_type,
        )
        self._add_todo(params_todo)
        ensure_child_reference(flow_root, step_id)


