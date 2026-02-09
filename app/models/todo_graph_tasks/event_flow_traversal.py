"""事件流遍历流程（人类/AI 两种模式）"""

from __future__ import annotations

from collections import deque
from typing import Callable, Dict, Iterable, List, Optional, Set

from app.models import TodoItem
from app.models.todo_graph_tasks.dynamic_port_steps import DynamicPortStepPlanner
from app.models.todo_graph_tasks.edge_lookup import GraphEdgeLookup
from app.models.todo_graph_tasks.event_flow_emitters import EventFlowEmitters
from app.models.todo_graph_tasks.node_predicates import is_event_node
from engine.graph.models import GraphModel
from engine.utils.graph.graph_utils import is_flow_port_name


class EventFlowTraversal:
    def __init__(
        self,
        *,
        emitters: EventFlowEmitters,
        dynamic_steps: DynamicPortStepPlanner,
    ) -> None:
        self.emitters = emitters
        self.dynamic_steps = dynamic_steps

    def _collect_flow_scope_for_progress(
        self,
        *,
        start_id: str,
        edge_lookup: GraphEdgeLookup,
    ) -> tuple[Set[str], Set[str], List]:
        """为进度估算收集事件流范围内的节点与连线。

        返回：
        - flow_visited: 仅流程边可达的节点集合（用于 AI 模式按块筛选）
        - all_nodes: flow_visited + 其数据祖先节点（用于“总节点数”）
        - relevant_edges: 两端都在 all_nodes 的所有边（流程边 + 数据边）
        """
        flow_adj = edge_lookup.flow_adj
        incoming_edges_by_node = edge_lookup.incoming_edges_by_node
        flow_edge_ids = edge_lookup.flow_edge_ids
        edges_list = edge_lookup.edges_list

        flow_visited: Set[str] = set()
        queue: deque[str] = deque([start_id])
        flow_visited.add(start_id)
        while queue:
            current = queue.popleft()
            for _, next_id in flow_adj.get(current, []):
                if next_id not in flow_visited:
                    flow_visited.add(next_id)
                    queue.append(next_id)

        def collect_data_ancestors(node_id: str, accumulator: Set[str]) -> None:
            stack: List[str] = [node_id]
            while stack:
                current_target = stack.pop()
                for edge in incoming_edges_by_node.get(current_target, []):
                    if edge.id in flow_edge_ids:
                        continue
                    source_id = edge.src_node
                    if source_id not in accumulator:
                        accumulator.add(source_id)
                        stack.append(source_id)

        all_nodes: Set[str] = set(flow_visited)
        for node_id in list(flow_visited):
            collect_data_ancestors(node_id, all_nodes)

        relevant_edges = [
            edge for edge in edges_list if edge.src_node in all_nodes and edge.dst_node in all_nodes
        ]
        return (flow_visited, all_nodes, relevant_edges)

    def generate_human_mode_tasks(
        self,
        *,
        flow_root: TodoItem,
        flow_root_id: str,
        start_id: str,
        model: GraphModel,
        edge_lookup: GraphEdgeLookup,
        graph_id: str,
        template_ctx_id: str,
        instance_ctx_id: str,
        suppress_auto_jump: bool,
        task_type: str,
        progress_advance: Optional[Callable[[str, int, int], None]] = None,
        stage_text: str = "",
    ) -> None:
        flow_adj = edge_lookup.flow_adj
        input_edges_map = edge_lookup.input_edges_map
        visited: Set[str] = {start_id}
        queue: deque[str] = deque([start_id])
        connected_edge_ids: Set[str] = set()

        normalized_stage = str(stage_text or "生成事件流")
        if callable(progress_advance):
            _flow_visited, all_nodes, relevant_edges = self._collect_flow_scope_for_progress(
                start_id=start_id, edge_lookup=edge_lookup
            )
            progress_advance(
                normalized_stage,
                0,
                int(len(all_nodes) + len(relevant_edges)),
            )
            # 事件节点已在外层创建，这里计入完成度
            progress_advance(normalized_stage, 1, 0)

        pending_units_to_report = 0

        def _expand_data_dependencies_from_target(*, target_node_id: str) -> None:
            """从给定目标节点开始，沿数据边反向扩展整条数据依赖链。

            人类模式下“反向拖线创建数据节点”需要先有目标节点，再逐层向上游创建。
            因此这里按“发现即创建（下游在前，上游在后）”的队列顺序生成步骤。
            """
            nonlocal pending_units_to_report
            pending_target_ids: deque[str] = deque([target_node_id])
            expanded_target_ids: Set[str] = set()

            while pending_target_ids:
                current_target_id = pending_target_ids.popleft()
                if current_target_id in expanded_target_ids:
                    continue
                expanded_target_ids.add(current_target_id)

                current_target_node = model.nodes.get(current_target_id)
                if not current_target_node:
                    continue

                for input_port in current_target_node.inputs:
                    if is_flow_port_name(input_port.name):
                        continue

                    edges_for_input = input_edges_map.get((current_target_id, input_port.name), [])
                    for edge in edges_for_input:
                        data_node_id = edge.src_node
                        if data_node_id in visited:
                            continue

                        visited.add(data_node_id)
                        data_node = model.nodes.get(data_node_id)
                        if not data_node:
                            continue

                        self.emitters.create_data_node_step(
                            flow_root=flow_root,
                            flow_root_id=flow_root_id,
                            current_node=current_target_node,
                            data_node=data_node,
                            edge=edge,
                            model=model,
                            graph_id=graph_id,
                            template_ctx_id=template_ctx_id,
                            instance_ctx_id=instance_ctx_id,
                            suppress_auto_jump=suppress_auto_jump,
                            task_type=task_type,
                        )
                        pending_target_ids.append(data_node_id)
                        pending_units_to_report += 1
                        if pending_units_to_report >= 20 and callable(progress_advance):
                            progress_advance(normalized_stage, pending_units_to_report, 0)
                            pending_units_to_report = 0

        while queue:
            current = queue.popleft()
            current_node = model.nodes.get(current)

            if current_node:
                _expand_data_dependencies_from_target(target_node_id=current)

            branch_dyn_done: Set[str] = set()

            for edge, next_id in flow_adj.get(current, []):
                is_new = False
                if next_id not in visited:
                    visited.add(next_id)
                    queue.append(next_id)
                    is_new = True

                if not is_new:
                    continue

                prev_node = model.nodes.get(current)
                next_node = model.nodes.get(next_id)
                if not prev_node or not next_node:
                    continue
                if is_event_node(next_node):
                    continue

                if self.dynamic_steps.is_branching_node(prev_node) and prev_node.id not in branch_dyn_done:
                    self.dynamic_steps.attach_dynamic_steps(
                        flow_root=flow_root,
                        flow_root_id=flow_root_id,
                        graph_id=graph_id,
                        node_obj=prev_node,
                        template_ctx_id=template_ctx_id,
                        instance_ctx_id=instance_ctx_id,
                        suppress_auto_jump=suppress_auto_jump,
                        allow_branch_outputs=True,
                        task_type=task_type,
                    )
                    branch_dyn_done.add(prev_node.id)

                step_id = self.emitters.create_human_connection_step(
                    flow_root=flow_root,
                    flow_root_id=flow_root_id,
                    graph_id=graph_id,
                    prev_node=prev_node,
                    next_node=next_node,
                    edge=edge,
                    template_ctx_id=template_ctx_id,
                    instance_ctx_id=instance_ctx_id,
                    suppress_auto_jump=suppress_auto_jump,
                    task_type=task_type,
                )
                connected_edge_ids.add(edge.id)
                pending_units_to_report += 2
                if pending_units_to_report >= 20 and callable(progress_advance):
                    progress_advance(normalized_stage, pending_units_to_report, 0)
                    pending_units_to_report = 0

                if not self.dynamic_steps.is_branching_node(next_node):
                    self.dynamic_steps.attach_dynamic_steps(
                        flow_root=flow_root,
                        flow_root_id=flow_root_id,
                        graph_id=graph_id,
                        node_obj=next_node,
                        template_ctx_id=template_ctx_id,
                        instance_ctx_id=instance_ctx_id,
                        suppress_auto_jump=suppress_auto_jump,
                        allow_branch_outputs=False,
                        task_type=task_type,
                    )

                params_payload = self.dynamic_steps.collect_constant_params(next_node)
                self.dynamic_steps.ensure_type_step(
                    node_obj=next_node,
                    flow_root=flow_root,
                    flow_root_id=flow_root_id,
                    graph_id=graph_id,
                    template_ctx_id=template_ctx_id,
                    instance_ctx_id=instance_ctx_id,
                    suppress_auto_jump=suppress_auto_jump,
                    step_id=f"{step_id}:types",
                    params_payload=params_payload,
                    task_type=task_type,
                )
                self.dynamic_steps.ensure_param_step(
                    node_obj=next_node,
                    flow_root=flow_root,
                    flow_root_id=flow_root_id,
                    graph_id=graph_id,
                    template_ctx_id=template_ctx_id,
                    instance_ctx_id=instance_ctx_id,
                    suppress_auto_jump=suppress_auto_jump,
                    step_id=f"{step_id}:params",
                    params_payload=params_payload,
                    task_type=task_type,
                )

        remaining_edges = [
            edge
            for edge in edge_lookup.edges_list
            if edge.id not in connected_edge_ids and edge.src_node in visited and edge.dst_node in visited
        ]
        if remaining_edges:
            before = len(connected_edge_ids)
            self.emitters.handle_remaining_edges(
                flow_root=flow_root,
                flow_root_id=flow_root_id,
                remaining_edges=remaining_edges,
                model=model,
                connected_edge_ids=connected_edge_ids,
                graph_id=graph_id,
                template_ctx_id=template_ctx_id,
                instance_ctx_id=instance_ctx_id,
                suppress_auto_jump=suppress_auto_jump,
                task_type=task_type,
            )
            after = len(connected_edge_ids)
            delta_edges = int(after - before)
            if delta_edges > 0:
                pending_units_to_report += delta_edges

        if pending_units_to_report > 0 and callable(progress_advance):
            progress_advance(normalized_stage, pending_units_to_report, 0)

    def generate_ai_mode_tasks(
        self,
        *,
        flow_root: TodoItem,
        flow_root_id: str,
        start_id: str,
        model: GraphModel,
        edge_lookup: GraphEdgeLookup,
        graph_id: str,
        template_ctx_id: str,
        instance_ctx_id: str,
        suppress_auto_jump: bool,
        task_type: str,
        progress_advance: Optional[Callable[[str, int, int], None]] = None,
        stage_text: str = "",
    ) -> None:
        flow_visited, all_nodes, relevant_edges = self._collect_flow_scope_for_progress(
            start_id=start_id,
            edge_lookup=edge_lookup,
        )

        created_nodes: Set[str] = {start_id}
        connected_edge_ids: Set[str] = set()

        normalized_stage = str(stage_text or "生成事件流")
        if callable(progress_advance):
            progress_advance(
                normalized_stage,
                0,
                int(len(all_nodes) + len(relevant_edges)),
            )
            # 事件节点已在外层创建，这里计入完成度
            progress_advance(normalized_stage, 1, 0)

        def node_pos_key(node_id: str) -> tuple:
            node_obj = model.nodes.get(node_id)
            if not node_obj:
                return (0.0, 0.0)
            pos = getattr(node_obj, "pos", None)
            if isinstance(pos, (list, tuple)) and len(pos) >= 2:
                x_val, y_val = pos[0], pos[1]
            else:
                x_val = getattr(node_obj, "x", 0.0)
                y_val = getattr(node_obj, "y", 0.0)
            return (float(x_val), float(y_val))

        basic_blocks = getattr(model, "basic_blocks", []) or []
        related_blocks = [block for block in basic_blocks if any(node in flow_visited for node in block.nodes)]
        event_block = next((block for block in related_blocks if start_id in block.nodes), None)
        ordered_blocks = ([event_block] if event_block else []) + [
            block for block in related_blocks if block is not event_block
        ]

        for block in ordered_blocks:
            in_block = [node for node in block.nodes if node in all_nodes and node != start_id and node not in created_nodes]
            in_block_sorted = sorted(in_block, key=node_pos_key)

            created_in_block = self.emitters.create_node_batch(
                node_ids=in_block_sorted,
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
            if created_in_block and callable(progress_advance):
                progress_advance(normalized_stage, int(len(created_in_block)), 0)

        leftovers = [node for node in all_nodes if node not in created_nodes and node != start_id]
        if leftovers:
            leftover_created_nodes = self.emitters.handle_leftover_nodes(
                flow_root=flow_root,
                flow_root_id=flow_root_id,
                leftovers=leftovers,
                model=model,
                created_nodes=created_nodes,
                graph_id=graph_id,
                template_ctx_id=template_ctx_id,
                instance_ctx_id=instance_ctx_id,
                suppress_auto_jump=suppress_auto_jump,
                node_pos_key=node_pos_key,
                task_type=task_type,
            )
            if leftover_created_nodes and callable(progress_advance):
                progress_advance(normalized_stage, int(len(leftover_created_nodes)), 0)

        if relevant_edges:
            before = len(connected_edge_ids)
            self.emitters.build_connection_steps(
                flow_root=flow_root,
                flow_root_id=flow_root_id,
                edges_to_connect=relevant_edges,
                model=model,
                connected_edge_ids=connected_edge_ids,
                graph_id=graph_id,
                template_ctx_id=template_ctx_id,
                instance_ctx_id=instance_ctx_id,
                suppress_auto_jump=suppress_auto_jump,
                task_type=task_type,
            )
            after = len(connected_edge_ids)
            delta_edges = int(after - before)
            if delta_edges > 0 and callable(progress_advance):
                progress_advance(normalized_stage, delta_edges, 0)

    def generate_ai_node_by_node_tasks(
        self,
        *,
        flow_root: TodoItem,
        flow_root_id: str,
        start_id: str,
        model: GraphModel,
        edge_lookup: GraphEdgeLookup,
        graph_id: str,
        template_ctx_id: str,
        instance_ctx_id: str,
        suppress_auto_jump: bool,
        task_type: str,
        progress_advance: Optional[Callable[[str, int, int], None]] = None,
        stage_text: str = "",
    ) -> None:
        flow_visited, all_nodes, relevant_edges = self._collect_flow_scope_for_progress(
            start_id=start_id,
            edge_lookup=edge_lookup,
        )

        created_nodes: Set[str] = {start_id}
        connected_edge_ids: Set[str] = set()

        normalized_stage = str(stage_text or "生成事件流")
        if callable(progress_advance):
            progress_advance(
                normalized_stage,
                0,
                int(len(all_nodes) + len(relevant_edges)),
            )
            # 事件节点已在外层创建，这里计入完成度
            progress_advance(normalized_stage, 1, 0)

        def node_pos_key(node_id: str) -> tuple:
            node_obj = model.nodes.get(node_id)
            if not node_obj:
                return (0.0, 0.0)
            pos = getattr(node_obj, "pos", None)
            if isinstance(pos, (list, tuple)) and len(pos) >= 2:
                x_val, y_val = pos[0], pos[1]
            else:
                x_val = getattr(node_obj, "x", 0.0)
                y_val = getattr(node_obj, "y", 0.0)
            return (float(x_val), float(y_val))

        basic_blocks = getattr(model, "basic_blocks", []) or []
        related_blocks = [block for block in basic_blocks if any(node in flow_visited for node in block.nodes)]
        event_block = next((block for block in related_blocks if start_id in block.nodes), None)
        ordered_blocks = ([event_block] if event_block else []) + [
            block for block in related_blocks if block is not event_block
        ]

        for block in ordered_blocks:
            in_block = [node for node in block.nodes if node in all_nodes and node != start_id and node not in created_nodes]
            in_block_sorted = sorted(in_block, key=node_pos_key)
            created_in_block: List[str] = []
            for node_id in in_block_sorted:
                created = self.emitters.create_node_with_immediate_config(
                    node_id=node_id,
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
                if created:
                    created_in_block.append(node_id)
            if created_in_block and callable(progress_advance):
                progress_advance(normalized_stage, int(len(created_in_block)), 0)

        leftovers = [node for node in all_nodes if node not in created_nodes and node != start_id]
        if leftovers:
            leftovers_sorted = sorted(leftovers, key=node_pos_key)
            created_leftovers: List[str] = []
            for node_id in leftovers_sorted:
                created = self.emitters.create_node_with_immediate_config(
                    node_id=node_id,
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
                if created:
                    created_leftovers.append(node_id)
            if created_leftovers and callable(progress_advance):
                progress_advance(normalized_stage, int(len(created_leftovers)), 0)

        if relevant_edges:
            before = len(connected_edge_ids)
            self.emitters.build_connection_steps(
                flow_root=flow_root,
                flow_root_id=flow_root_id,
                edges_to_connect=relevant_edges,
                model=model,
                connected_edge_ids=connected_edge_ids,
                graph_id=graph_id,
                template_ctx_id=template_ctx_id,
                instance_ctx_id=instance_ctx_id,
                suppress_auto_jump=suppress_auto_jump,
                task_type=task_type,
            )
            after = len(connected_edge_ids)
            delta_edges = int(after - before)
            if delta_edges > 0 and callable(progress_advance):
                progress_advance(normalized_stage, delta_edges, 0)


