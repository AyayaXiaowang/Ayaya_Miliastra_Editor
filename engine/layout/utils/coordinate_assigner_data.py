"""
数据节点坐标规划工具。

本模块承载数据节点在布局阶段的列内排序与 Y 轴决策逻辑，保持纯计算特性：
- 仅依赖 `BlockLayoutContext` 与预先计算的 `node_x_position`；
- 通过 `DataNodePlacementPlan` 与 `DataNodeYDebugSnapshot` 将结果与调试信息回传给调用方；
- 不直接写回 `context.node_local_pos` 或调试字典，便于单元测试与重用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
import math

from ..blocks.block_layout_context import BlockLayoutContext
from ..core.constants import UI_NODE_PADDING
from ..utils.graph_query_utils import InputPortLayoutPlan, build_input_port_layout_plan


@dataclass(frozen=True)
class DataNodePlacementCandidate:
    """
    单个数据节点在列内排序阶段的候选信息。

    - `x_position`: 预先计算的槽位浮点列索引；
    - `x_key`: 取整后的列键，用于在同一列内聚合；
    - `min_chain_id`: 该节点参与的所有链条中的最小 ID，用作“链优先级”稳定排序；
    - `order_index`: 节点在 `data_nodes_in_order` 中的基准顺序；
    - `stack_order_hint`: 来自上游堆叠器的排序提示，作为列内稳定栈顺序。
    """

    node_id: str
    x_position: float
    x_key: int
    min_chain_id: int
    order_index: int
    stack_order_hint: int

    def sort_key(self) -> tuple[int, int, int, str]:
        """
        列内排序关键字。

        规则：
        - 先按 X 列从右到左（列索引越大越先布局）；
        - 同列内按链 ID、堆叠提示与原始顺序稳定排序。
        """
        return (
            -self.x_key,
            self.min_chain_id,
            self.stack_order_hint,
            self.order_index,
            self.node_id,
        )


@dataclass
class DataColumnBottomState:
    """
    记录当前每一列的“底部 Y 值”，用于保证列内节点不重叠。
    """

    bottoms_by_column: dict[int, float]

    def seed_with_flow_bottom(self, column_key: int, flow_bottom: float, flow_to_data_gap: float) -> None:
        """
        使用给定列上的流程节点底部高度为数据节点提供初始列底。

        若已有更大的列底，则保持原值不变。
        """
        if flow_bottom <= 0.0:
            return
        seeded_bottom = flow_bottom + flow_to_data_gap
        current_bottom = self.bottoms_by_column.get(column_key, 0.0)
        if seeded_bottom > current_bottom:
            self.bottoms_by_column[column_key] = seeded_bottom

    def update_after_node(self, column_key: int, node_top_y: float, node_height: float, stack_gap: float) -> None:
        """
        在列内放置一个节点后，更新该列的底部高度。
        """
        self.bottoms_by_column[column_key] = node_top_y + node_height + stack_gap


@dataclass
class DataNodeYDebugSnapshot:
    """
    单个数据节点 Y 轴决策的调试快照。

    调用方可将本结构转存到调试字典中，用于 UI 叠加与日志输出。
    """

    final_y: float
    base_y: float
    node_height: float
    strict_column_bottom: float
    start_y_from_above: float
    start_y_from_chain_ports: float
    start_y_from_single_target: Optional[float]
    start_y_from_multi_targets_mid: Optional[float]
    forced_by_multi_targets: bool
    chain_raw_port_y: float
    chain_port_debug: list[dict]


@dataclass
class DataNodePlacementPlan:
    """
    数据节点最终坐标的规划结果。

    包含节点 ID、最终坐标和完整的调试快照。
    """

    node_id: str
    x_coordinate: float
    y_coordinate: float
    debug_snapshot: DataNodeYDebugSnapshot


class DataCoordinatePlanner:
    """
    数据节点坐标规划器。

    负责在给定 `BlockLayoutContext` 与列索引映射的前提下，为所有数据节点
    计算不重叠的 Y 坐标，并生成可供调试的快照信息。
    """

    def __init__(
        self,
        context: BlockLayoutContext,
        node_x_position: dict[str, float],
        slot_width: float,
    ):
        self.context = context
        self.node_x_position = node_x_position
        self.slot_width = float(slot_width)

        # 局部缓存，避免在同一布局过程中重复解析链条和端口布局
        self._chain_port_info_cache: dict[str, tuple[list[float], list[dict]]] = {}
        self._input_port_plan_cache: dict[str, InputPortLayoutPlan] = {}
        self._data_out_edges_cache: dict[str, List] = {}
        self._target_connected_ports_cache: dict[str, List[str]] = {}

    # ------------------------------------------------------------------
    # 对外入口
    # ------------------------------------------------------------------

    def build_data_node_candidates(self) -> list[DataNodePlacementCandidate]:
        """
        根据上下文构造所有数据节点的排序候选。

        该方法不修改 `context`，仅依赖预先计算的 `node_x_position`。
        """
        large_value = 10**9
        candidates: list[DataNodePlacementCandidate] = []

        for index, node_id in enumerate(self.context.data_nodes_in_order):
            x_position = self.node_x_position.get(node_id, 0.0)
            x_key = int(round(x_position))
            chain_ids = self.context.data_chain_ids_by_node.get(node_id) or []
            min_chain_id = min(chain_ids) if chain_ids else large_value
            stack_hint = self.context.node_stack_order.get(node_id, index)
            candidates.append(
                DataNodePlacementCandidate(
                    node_id=node_id,
                    x_position=x_position,
                    x_key=x_key,
                    min_chain_id=min_chain_id,
                    order_index=index,
                    stack_order_hint=int(stack_hint),
                )
            )

        return candidates

    def plan_data_node_coordinates(self) -> list[DataNodePlacementPlan]:
        """
        生成所有数据节点的坐标规划结果。

        过程：
        1. 右→左构造排序候选；
        2. 维护每一列的列底状态，逐个节点选择合适的 Y 坐标；
        3. 返回包含调试快照的 `DataNodePlacementPlan` 列表。
        """
        column_state = DataColumnBottomState(bottoms_by_column={})
        sorted_candidates = sorted(self.build_data_node_candidates(), key=lambda candidate: candidate.sort_key())
        placement_plans: list[DataNodePlacementPlan] = []

        for candidate in sorted_candidates:
            flow_bottom = self.context.flow_bottom_by_slot.get(candidate.x_key, 0.0)
            column_state.seed_with_flow_bottom(candidate.x_key, flow_bottom, self.context.flow_to_data_gap)

            final_y, debug_snapshot = self._decide_data_node_y(
                candidate.node_id,
                candidate.x_position,
                candidate.x_key,
                column_state.bottoms_by_column,
            )
            x_coordinate = candidate.x_position * self.slot_width
            placement_plans.append(
                DataNodePlacementPlan(
                    node_id=candidate.node_id,
                    x_coordinate=x_coordinate,
                    y_coordinate=final_y,
                    debug_snapshot=debug_snapshot,
                )
            )

            column_state.update_after_node(
                candidate.x_key,
                final_y,
                debug_snapshot.node_height,
                self.context.data_stack_gap,
            )

        return placement_plans

    # ------------------------------------------------------------------
    # Y 坐标决策核心
    # ------------------------------------------------------------------

    def _decide_data_node_y(
        self,
        data_id: str,
        x_position: float,
        x_key: int,
        x_column_bottom_y: dict[int, float],
    ) -> tuple[float, DataNodeYDebugSnapshot]:
        """
        计算数据节点的 Y 坐标，并返回最终高度及调试快照。
        """
        (
            start_y_from_above,
            start_y_from_chain_ports,
            start_y_from_single_target,
            start_y_from_multi_targets_mid,
            chain_raw_port_y,
            chain_port_debug,
        ) = self._collect_y_candidates(data_id, x_key, x_column_bottom_y)

        forced_by_multi_targets = start_y_from_multi_targets_mid is not None
        if forced_by_multi_targets:
            base_y = float(start_y_from_multi_targets_mid)
        else:
            # 取所有候选中的最大值（最下面的）
            start_y_candidates: list[float] = []
            if start_y_from_above > 0.0:
                start_y_candidates.append(start_y_from_above)
            if start_y_from_chain_ports > 0.0:
                start_y_candidates.append(start_y_from_chain_ports)
            if start_y_from_single_target is not None:
                start_y_candidates.append(start_y_from_single_target)
            base_y = max(start_y_candidates) if start_y_candidates else 0.0

        node_height = self.context.get_estimated_node_height(data_id)
        final_y = base_y

        # 额外硬性夹紧：同列严格不重叠（即使候选中未选到列底，也强制不高于列底）
        strict_column_bottom = x_column_bottom_y.get(x_key, 0.0)
        if final_y < strict_column_bottom:
            final_y = strict_column_bottom

        debug_snapshot = DataNodeYDebugSnapshot(
            final_y=float(final_y),
            base_y=float(base_y),
            node_height=float(node_height),
            strict_column_bottom=float(strict_column_bottom),
            start_y_from_above=float(start_y_from_above),
            start_y_from_chain_ports=float(start_y_from_chain_ports),
            start_y_from_single_target=float(start_y_from_single_target) if start_y_from_single_target is not None else None,
            start_y_from_multi_targets_mid=float(start_y_from_multi_targets_mid)
            if start_y_from_multi_targets_mid is not None
            else None,
            forced_by_multi_targets=forced_by_multi_targets,
            chain_raw_port_y=float(chain_raw_port_y),
            chain_port_debug=chain_port_debug,
        )

        return final_y, debug_snapshot

    def _collect_y_candidates(
        self,
        data_id: str,
        x_key: int,
        x_column_bottom_y: dict[int, float],
    ) -> tuple[float, float, Optional[float], Optional[float], float, list[dict]]:
        """
        收集单个数据节点 Y 坐标的所有候选值。

        返回：
            (start_y_from_above, start_y_from_chain_ports, start_y_from_single_target,
             start_y_from_multi_targets_mid, chain_raw_port_y, chain_port_debug)
        """
        out_edges = self._get_out_edges_cached(data_id)

        # 候选1：如果该 X 列已有节点，必须在其下方
        start_y_from_above = x_column_bottom_y.get(x_key, 0.0)

        # 候选2：如果上方没有节点，使用“该节点所属链条的消费者端口实际 Y + 安全间距”
        start_y_from_chain_ports = self._get_min_chain_port_y(data_id)

        # 为详细调试采集“端口原始 Y”和明细
        chain_raw_port_y, chain_port_debug = self._collect_chain_port_debug_info(data_id)

        # 候选3：如果右侧只有一根连线且目标节点左侧也只有一个输入，使用目标节点的 Y
        start_y_from_single_target = self._get_single_target_y(data_id, out_edges)

        # 优先规则：若右侧存在至少两个直接纯数据目标，使用这些目标 Y 的上下界中点 (min+max)/2
        start_y_from_multi_targets_mid = self._get_multi_targets_mid_y(data_id, out_edges)

        return (
            start_y_from_above,
            start_y_from_chain_ports,
            start_y_from_single_target,
            start_y_from_multi_targets_mid,
            chain_raw_port_y,
            chain_port_debug,
        )

    def _collect_chain_port_debug_info(self, data_id: str) -> tuple[float, list[dict]]:
        """
        收集链条端口的调试信息。

        返回：
            (chain_raw_port_y, chain_port_debug)
        """
        chain_raw_port_y = 0.0
        port_y_values, chain_port_debug = self._resolve_chain_port_info(data_id)

        if port_y_values:
            if len(port_y_values) > 1:
                chain_raw_port_y = (min(port_y_values) + max(port_y_values)) / 2.0
            else:
                chain_raw_port_y = port_y_values[0]

        return chain_raw_port_y, chain_port_debug

    def _resolve_chain_port_info(self, data_id: str) -> tuple[list[float], list[dict]]:
        """
        解析链条端口的几何信息并进行缓存，避免重复遍历。
        """
        cached = self._chain_port_info_cache.get(data_id)
        if cached is not None:
            return cached

        port_y_values: list[float] = []
        chain_port_debug: list[dict] = []
        chain_ids_for_debug = self.context.data_chain_ids_by_node.get(data_id, [])

        if chain_ids_for_debug:
            for chain_id in chain_ids_for_debug:
                target_flow_id = self.context.chain_target_flow.get(chain_id)
                if not target_flow_id or target_flow_id not in self.context.flow_id_set:
                    continue

                consumer_port_name = self.context.chain_consumer_port_name.get(chain_id)
                consumer_port_index = self.context.chain_consumer_port_index.get(chain_id)
                resolved_name = consumer_port_name
                port_index_num: Optional[int] = None

                if resolved_name is None and consumer_port_index is not None:
                    flow_node_obj = self.context.model.nodes.get(target_flow_id)
                    if not flow_node_obj:
                        continue
                    index = int(consumer_port_index)
                    if index < 0 or index >= len(flow_node_obj.inputs):
                        continue
                    resolved_name = flow_node_obj.inputs[index].name
                    port_index_num = index

                if resolved_name is None:
                    continue

                port_y = self._compute_flow_port_y(target_flow_id, resolved_name)
                if port_y <= 0.0:
                    continue

                if port_index_num is None:
                    port_index_num = self.context.get_input_port_index(target_flow_id, resolved_name)

                port_y_values.append(port_y)
                chain_port_debug.append(
                    {
                        "flow_id": target_flow_id,
                        "port_index": int(port_index_num) if port_index_num is not None else None,
                        "port_name": resolved_name,
                        "port_y": float(port_y),
                    }
                )

        result = (port_y_values, chain_port_debug)
        self._chain_port_info_cache[data_id] = result
        return result

    def _get_min_chain_port_y(self, data_id: str) -> float:
        """
        获取该数据节点所属链条中“消费者流程节点的输入端口”的实际 Y 坐标候选。

        多链时：收集所有相关消费者端口的实际 Y，返回上下界中点 ((min+max)/2)。
        如果该节点不属于任何链条或未能成功解析端口，则回退到当前列的流程底部 + 安全间隔。
        """
        chain_ids = self.context.data_chain_ids_by_node.get(data_id, [])

        if not chain_ids:
            x_position = self.node_x_position.get(data_id, 0.0)
            x_key = int(round(x_position))
            flow_bottom = self.context.flow_bottom_by_slot.get(x_key, 0.0)
            return flow_bottom + self.context.flow_to_data_gap

        port_y_values, _ = self._resolve_chain_port_info(data_id)

        if not port_y_values:
            x_position = self.node_x_position.get(data_id, 0.0)
            x_key = int(round(x_position))
            flow_bottom = self.context.flow_bottom_by_slot.get(x_key, 0.0)
            return flow_bottom + self.context.flow_to_data_gap

        if len(port_y_values) > 1:
            aggregated = (min(port_y_values) + max(port_y_values)) / 2.0
        else:
            aggregated = port_y_values[0]
        return aggregated + self.context.input_port_to_data_gap

    def _compute_flow_port_y(self, flow_node_id: str, port_name: str) -> float:
        """
        计算流程节点某个输入端口的 Y 坐标（与 UI 一致的精确算法）。
        """
        if flow_node_id not in self.context.node_local_pos:
            return 0.0
        plan = self._get_input_port_layout_plan(flow_node_id)
        if plan is None:
            return 0.0
        row_index = plan.row_index_by_port.get(str(port_name))
        if row_index is None:
            return 0.0
        flow_top_y = float(self.context.node_local_pos[flow_node_id][1])
        input_start_y = flow_top_y + float(self.context.ui_node_header_height) + float(UI_NODE_PADDING)
        center_offset = float(self.context.ui_row_height) / 2.0
        port_center_y = input_start_y + float(row_index) * float(self.context.ui_row_height) + center_offset
        return float(port_center_y)

    def _get_single_target_y(self, data_id: str, out_edges: Optional[List] = None) -> Optional[float]:
        """
        检查右侧连接情况，根据目标节点的输入端口数量和位置返回调整后的 Y 坐标。

        规则：
        1. 遍历当前节点的所有输出连线；
        2. 对每个连接到纯数据节点的连线，根据目标节点的输入端口情况计算候选 Y；
        3. 若目标节点拥有多个有连线的输入，则仅考虑中间及下半部分端口：
           - 中间端口（奇数个且居中）：候选 Y = 目标节点顶部 Y；
           - 下半部分端口：候选 Y = 目标 Y + 距离中心端口数 × 节点高度；
        4. 返回所有候选中的最大值（最下面的），若无候选则返回 None。
        """
        out_edges = out_edges if out_edges is not None else self.context.get_data_out_edges(data_id)

        if not out_edges:
            return None

        candidate_y_values: list[float] = []

        for target_edge in out_edges:
            target_node_id = target_edge.dst_node
            target_port = target_edge.dst_port

            if not self.context.is_pure_data_node(target_node_id):
                continue

            if target_node_id not in self.context.node_local_pos:
                continue

            target_node_obj = self.context.model.nodes.get(target_node_id)
            if not target_node_obj:
                continue

            target_in_edges = self.context.get_data_in_edges(target_node_id)

            connected_ports_ordered = self._target_connected_ports_cache.get(target_node_id)
            if connected_ports_ordered is None:
                ports_with_edges = {str(edge.dst_port) for edge in target_in_edges if edge.dst_port}
                if not ports_with_edges:
                    self._target_connected_ports_cache[target_node_id] = []
                    continue
                port_plan = build_input_port_layout_plan(target_node_obj, ports_with_edges)
                connected_ports_ordered = [
                    port_name for port_name in port_plan.render_inputs if port_name in ports_with_edges
                ]
                self._target_connected_ports_cache[target_node_id] = connected_ports_ordered
            if not connected_ports_ordered:
                continue

            total_connected = len(connected_ports_ordered)
            if total_connected <= 1:
                continue

            target_port_name = str(target_port)
            if target_port_name not in connected_ports_ordered:
                continue
            current_position = connected_ports_ordered.index(target_port_name) + 1

            if total_connected % 2 == 1:
                center_position = (total_connected + 1) / 2.0
            else:
                center_position = total_connected / 2.0 + 0.5

            target_base_y = self.context.node_local_pos[target_node_id][1]

            if current_position < center_position:
                continue

            if current_position == center_position:
                candidate_y_values.append(target_base_y)
                continue

            distance_from_center = current_position - center_position
            steps = int(math.ceil(distance_from_center))
            current_node_height = self.context.get_estimated_node_height(data_id)
            candidate_y_values.append(target_base_y + steps * current_node_height)

        if candidate_y_values:
            return max(candidate_y_values)
        else:
            return None

    def _get_multi_targets_mid_y(self, data_id: str, out_edges: Optional[List] = None) -> Optional[float]:
        """
        当当前数据节点右侧存在多个直接纯数据目标时，计算它们 Y 的中点：
        返回这些目标节点顶部 Y 的 (min+max)/2；若目标不足 2 个或未就绪则返回 None。
        """
        out_edges = out_edges if out_edges is not None else self.context.get_data_out_edges(data_id)
        if not out_edges:
            return None
        y_values: list[float] = []
        for edge in out_edges:
            target_id = edge.dst_node
            if not self.context.is_pure_data_node(target_id):
                continue
            if target_id not in self.context.node_local_pos:
                continue
            y_values.append(float(self.context.node_local_pos[target_id][1]))
        if len(y_values) < 2:
            return None
        return (min(y_values) + max(y_values)) / 2.0

    def _get_out_edges_cached(self, node_id: str) -> List:
        """
        带缓存地获取数据节点的所有输出边。
        """
        cached = self._data_out_edges_cache.get(node_id)
        if cached is not None:
            return cached
        edges = list(self.context.get_data_out_edges(node_id))
        self._data_out_edges_cache[node_id] = edges
        return edges

    def _get_input_port_layout_plan(self, flow_node_id: str) -> Optional[InputPortLayoutPlan]:
        """
        带缓存地获取流程节点的输入端口布局计划。
        """
        cached = self._input_port_plan_cache.get(flow_node_id)
        if cached is not None:
            return cached
        flow_node_obj = self.context.model.nodes.get(flow_node_id)
        if not flow_node_obj:
            return None
        connected_input_ports: Set[str] = set()
        for edge in self.context.get_data_in_edges(flow_node_id):
            if edge.dst_port:
                connected_input_ports.add(str(edge.dst_port))
        plan = build_input_port_layout_plan(flow_node_obj, connected_input_ports)
        self._input_port_plan_cache[flow_node_id] = plan
        return plan


