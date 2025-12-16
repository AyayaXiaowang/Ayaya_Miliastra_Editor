from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from app.models import TodoItem
from app.models.todo_block_index_helper import build_node_block_index, resolve_block_index_for_todo
from app.models.todo_graph_tasks.dynamic_port_steps import DynamicPortStepPlanner
from app.models.todo_graph_tasks.edge_lookup import GraphEdgeLookup
from app.models.todo_graph_tasks.event_flow_emitters import EventFlowEmitters
from app.models.todo_graph_tasks.event_flow_traversal import EventFlowTraversal
from app.models.todo_graph_tasks.node_predicates import is_event_node
from app.models.todo_node_type_helper import NodeTypeHelper
from app.models.todo_pipeline.step_mode import GraphStepMode
from engine.graph.models import GraphModel
from engine.layout import LayoutService
from engine.utils.graph.graph_utils import is_flow_port_name
from engine.utils.name_utils import dedupe_preserve_order


class EventFlowTaskBuilder:
    def __init__(
        self,
        type_helper: NodeTypeHelper,
        add_todo: Callable[[TodoItem], None],
        todo_map: Dict[str, TodoItem],
    ) -> None:
        self.type_helper = type_helper
        self.todo_map = todo_map
        self.dynamic_steps = DynamicPortStepPlanner(
            type_helper=type_helper,
            add_todo=add_todo,
            todo_map=todo_map,
        )
        self.emitters = EventFlowEmitters(
            add_todo=add_todo,
            dynamic_steps=self.dynamic_steps,
        )
        self.traversal = EventFlowTraversal(
            emitters=self.emitters,
            dynamic_steps=self.dynamic_steps,
        )

    def build_event_flows(
        self,
        graph_root_id: str,
        graph_id: str,
        model: GraphModel,
        edge_lookup: GraphEdgeLookup,
        template_ctx_id: str,
        instance_ctx_id: str,
        suppress_auto_jump: bool,
        preview_template_id: str,
        graph_root: TodoItem,
        task_type: str,
        signal_param_types_by_node: Optional[Dict[str, Dict[str, str]]] = None,
    ) -> None:
        event_starts = self._collect_event_start_nodes(model, edge_lookup)
        if not event_starts:
            return

        mode = GraphStepMode.current()
        if not mode.is_human:
            LayoutService.compute_layout(model, clone_model=False)

        # 为当前图注册边索引与信号参数上下文，供动态端口/参数步骤规划复用
        self.dynamic_steps.set_graph_context(edge_lookup)
        if signal_param_types_by_node is not None:
            self.dynamic_steps.set_signal_param_types(signal_param_types_by_node)
            self.emitters.set_signal_param_types(signal_param_types_by_node)
        else:
            self.emitters.set_signal_param_types({})
        try:
            for start_id in event_starts:
                start_node = model.nodes.get(start_id)
                if not start_node:
                    continue
                from engine.graph.common import SIGNAL_LISTEN_NODE_TITLE
                flow_root = self.emitters.create_flow_root(
                    graph_root=graph_root,
                    graph_root_id=graph_root_id,
                    graph_id=graph_id,
                    start_node_id=start_id,
                    start_node_title=start_node.title,
                    template_ctx_id=template_ctx_id,
                    instance_ctx_id=instance_ctx_id,
                    suppress_auto_jump=suppress_auto_jump,
                    preview_template_id=preview_template_id,
                    task_type=task_type,
                )
                self.emitters.create_event_start_step(
                    flow_root=flow_root,
                    flow_root_id=flow_root.todo_id,
                    graph_id=graph_id,
                    start_node=start_node,
                    template_ctx_id=template_ctx_id,
                    instance_ctx_id=instance_ctx_id,
                    suppress_auto_jump=suppress_auto_jump,
                    task_type=task_type,
                )

                if getattr(start_node, "title", "") == SIGNAL_LISTEN_NODE_TITLE:
                    self.emitters.ensure_signal_binding_for_event_start(
                        flow_root=flow_root,
                        flow_root_id=flow_root.todo_id,
                        graph_id=graph_id,
                        start_node=start_node,
                        template_ctx_id=template_ctx_id,
                        instance_ctx_id=instance_ctx_id,
                        suppress_auto_jump=suppress_auto_jump,
                        task_type=task_type,
                        model=model,
                    )

                if mode.is_human:
                    self.traversal.generate_human_mode_tasks(
                        flow_root=flow_root,
                        flow_root_id=flow_root.todo_id,
                        start_id=start_id,
                        model=model,
                        edge_lookup=edge_lookup,
                        graph_id=graph_id,
                        template_ctx_id=template_ctx_id,
                        instance_ctx_id=instance_ctx_id,
                        suppress_auto_jump=suppress_auto_jump,
                        task_type=task_type,
                    )
                else:
                    self.traversal.generate_ai_mode_tasks(
                        flow_root=flow_root,
                        flow_root_id=flow_root.todo_id,
                        start_id=start_id,
                        model=model,
                        edge_lookup=edge_lookup,
                        graph_id=graph_id,
                        template_ctx_id=template_ctx_id,
                        instance_ctx_id=instance_ctx_id,
                        suppress_auto_jump=suppress_auto_jump,
                        task_type=task_type,
                    )

                self._reorder_flow_children_for_data_edges(flow_root=flow_root, model=model)
        finally:
            # 单次图任务完成后清理上下文，避免跨图复用
            self.dynamic_steps.clear_graph_context()
            self.dynamic_steps.clear_signal_param_types()
            self.emitters.clear_signal_param_types()

    def _collect_event_start_nodes(
        self,
        model: GraphModel,
        edge_lookup: GraphEdgeLookup,
    ) -> List[str]:
        def flow_in_degree(node_id: str) -> int:
            return edge_lookup.flow_in_degree_map.get(node_id, 0)

        def has_flow_out(node_id: str) -> bool:
            return bool(edge_lookup.flow_adj.get(node_id))

        candidates: List[str] = []
        for node_id, node in model.nodes.items():
            if is_event_node(node):
                candidates.append(node_id)
            elif flow_in_degree(node_id) == 0 and has_flow_out(node_id):
                candidates.append(node_id)

        if not candidates:
            for node_id, node in model.nodes.items():
                if any(is_flow_port_name(port.name) for port in node.inputs + node.outputs):
                    candidates = [node_id]
                    break

        def event_pos_key(node_id: str) -> tuple:
            node_obj = model.nodes.get(node_id)
            if node_obj and isinstance(node_obj.pos, tuple) and len(node_obj.pos) >= 2:
                x_val, y_val = node_obj.pos
                return (float(y_val), float(x_val), node_id)
            return (0.0, 0.0, node_id)

        unique_ids = dedupe_preserve_order(candidates)
        unique_ids.sort(key=event_pos_key)
        return unique_ids

    def _reorder_flow_children_for_data_edges(
        self,
        *,
        flow_root: TodoItem,
        model: GraphModel,
    ) -> None:
        """在同一 BasicBlock 内，为同一节点的“数据出口”连线步骤优先排序。

        仅在事件流子步骤已经生成完成后，对 `flow_root.children` 中的
        `graph_connect`/`graph_connect_merged` 步骤做块内的局部重排：
        - 不跨越非连线步骤（创建节点/动态端口/参数配置等位置保持不变）；
        - 同一块内，若某节点同时存在“作为目标的连线”和“作为源的连线”，
          则优先排列“以该节点为源”的连接步骤。
        """
        if not flow_root.children:
            return

        node_block_index = build_node_block_index(model)
        if not node_block_index:
            return

        children_ids: List[str] = list(flow_root.children)
        block_to_conn_indices: Dict[int, List[int]] = {}

        for index, todo_id in enumerate(children_ids):
            step = self.todo_map.get(todo_id)
            if not step:
                continue
            info = step.detail_info or {}
            detail_type = str(info.get("type", ""))
            if detail_type not in {"graph_connect", "graph_connect_merged"}:
                continue
            block_index = resolve_block_index_for_todo(step, node_block_index)
            if block_index is None:
                continue
            block_to_conn_indices.setdefault(block_index, []).append(index)

        if not block_to_conn_indices:
            return

        def _extract_connection_nodes(step: TodoItem) -> Optional[Tuple[str, str]]:
            info = step.detail_info or {}
            detail_type = str(info.get("type", ""))
            if detail_type == "graph_connect":
                src_id = str(info.get("src_node", "") or "")
                dst_id = str(info.get("dst_node", "") or "")
            elif detail_type == "graph_connect_merged":
                src_id = str(info.get("node1_id", "") or "")
                dst_id = str(info.get("node2_id", "") or "")
            else:
                return None
            if not src_id or not dst_id:
                return None
            return (src_id, dst_id)

        for _block_index, conn_indices in block_to_conn_indices.items():
            if not conn_indices or len(conn_indices) <= 1:
                continue

            # 提取该块内所有连接步骤的本地列表与源/目标节点。
            local_ids: List[str] = [children_ids[index] for index in conn_indices]
            local_src_ids: List[str] = []
            local_dst_ids: List[str] = []
            node_to_out_indices: Dict[str, List[int]] = {}
            node_to_in_indices: Dict[str, List[int]] = {}

            for local_index, step_id in enumerate(local_ids):
                step_obj = self.todo_map.get(step_id)
                nodes = _extract_connection_nodes(step_obj) if step_obj else None
                if not nodes:
                    local_src_ids.append("")
                    local_dst_ids.append("")
                    continue
                src_id, dst_id = nodes
                local_src_ids.append(src_id)
                local_dst_ids.append(dst_id)
                if src_id:
                    node_to_out_indices.setdefault(src_id, []).append(local_index)
                if dst_id:
                    node_to_in_indices.setdefault(dst_id, []).append(local_index)

            pivot_nodes: List[str] = [
                node_id for node_id in node_to_out_indices.keys() if node_id in node_to_in_indices
            ]
            if not pivot_nodes:
                continue

            # 为“每个节点的出口连线在入口连线之前”建立偏序约束：
            # 对于同一节点 N，所有 src==N 的边必须排在所有 dst==N 的边之前。
            edge_count = len(local_ids)
            adjacency: Dict[int, List[int]] = {index: [] for index in range(edge_count)}
            indegree: List[int] = [0 for _ in range(edge_count)]

            for node_id in pivot_nodes:
                out_indices = node_to_out_indices.get(node_id, [])
                in_indices = node_to_in_indices.get(node_id, [])
                for out_index in out_indices:
                    for in_index in in_indices:
                        if out_index == in_index:
                            continue
                        adjacency[out_index].append(in_index)

            # 去重并统计入度。
            for source_index, neighbors in adjacency.items():
                if not neighbors:
                    continue
                unique_neighbors = sorted(set(neighbors))
                adjacency[source_index] = unique_neighbors
            for source_index, neighbors in adjacency.items():
                for target_index in neighbors:
                    indegree[target_index] += 1

            # 基于原始顺序做稳定拓扑排序；若约束存在环，则保持原顺序不动。
            remaining: set[int] = set(range(edge_count))
            topo_order: List[int] = []

            while remaining:
                candidate_indices = [index for index in remaining if indegree[index] == 0]
                if not candidate_indices:
                    topo_order = []
                    break
                next_index = min(candidate_indices)
                remaining.remove(next_index)
                topo_order.append(next_index)
                for target_index in adjacency[next_index]:
                    indegree[target_index] -= 1

            if not topo_order or len(topo_order) != edge_count:
                continue

            reordered_local_ids: List[str] = [local_ids[index] for index in topo_order]
            for offset, global_index in enumerate(conn_indices):
                children_ids[global_index] = reordered_local_ids[offset]

        flow_root.children = children_ids

