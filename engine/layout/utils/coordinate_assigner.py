"""
坐标分配器

根据槽位索引和堆叠顺序统一分配所有节点的 X 和 Y 坐标（阶段 2）。
"""

from __future__ import annotations

from ..blocks.block_layout_context import BlockLayoutContext
from ..core.constants import debug
from engine.configs.settings import settings
from .coordinate_assigner_x import compute_flow_x_positions, compute_data_x_positions
from .coordinate_assigner_data import DataCoordinatePlanner, DataNodeYDebugSnapshot, DataNodePlacementPlan


class CoordinateAssigner:
    """坐标分配器 - 根据槽位索引和堆叠顺序统一分配所有节点的 X 和 Y 坐标（阶段 2）。"""

    def __init__(
        self,
        context: BlockLayoutContext,
        slot_width: float,
        flow_y_base: float,
        data_y_spacing: float,
    ):
        """
        初始化坐标分配器。

        Args:
            context: 当前块的布局上下文，提供节点集合与链条信息。
            slot_width: 单个列槽位对应的 X 像素宽度。
            flow_y_base: 流程节点统一的 Y 基线。
            data_y_spacing: 数据节点默认的垂直间距（部分策略会在此基础上调整）。
        """
        self.context = context
        self.slot_width = slot_width
        self.flow_y_base = flow_y_base
        self.data_y_spacing = data_y_spacing

        # 用于存储计算出的 X 位置（绝对像素位置，而非槽位索引）
        self.node_x_position: dict[str, float] = {}

    def assign_all_coordinates(self) -> None:
        """
        统一分配所有节点的坐标。

        流程：
        1. 基于链条约束计算所有节点的列索引并转换为 X 坐标；
        2. 为流程节点分配统一的 Y 基线坐标；
        3. 记录每个列上的流程节点底部高度，供数据节点使用；
        4. 使用数据坐标规划器为数据节点分配不重叠的 Y 坐标并写回调试信息。
        """
        # 1. 计算所有节点的 X 位置（新算法）
        self._compute_x_positions_by_chain()

        # 2. 分配流程节点坐标（使用计算好的 X 位置）
        self._assign_flow_coordinates()

        # 3. 更新每个槽位的流程节点底部 Y 坐标
        self._update_flow_bottom_by_slot()

        # 4. 分配数据节点坐标（使用计算好的 X 位置）
        self._assign_data_coordinates()

    # ------------------------------------------------------------------
    # X 坐标分配
    # ------------------------------------------------------------------

    def _compute_x_positions_by_chain(self) -> None:
        """
        基于链条长度与流程约束计算所有节点的 X 位置（列索引）。

        - 流程节点：使用 `compute_flow_x_positions` 计算带权最长路径上的列；
        - 数据节点：使用 `compute_data_x_positions` 根据链条消费者位置向左回溯；
        - 结果统一写入 `self.node_x_position`，键为节点 ID。
        """
        flow_x_positions = compute_flow_x_positions(self.context)
        data_x_positions = compute_data_x_positions(self.context, flow_x_positions)
        self.node_x_position = {**flow_x_positions, **data_x_positions}

    # ------------------------------------------------------------------
    # 流程节点坐标分配
    # ------------------------------------------------------------------

    def _assign_flow_coordinates(self) -> None:
        """分配流程节点坐标（使用计算好的 X 位置，Y 使用统一基线）。"""
        for flow_node_id in self.context.flow_node_ids:
            x_position = self.node_x_position.get(flow_node_id, 0.0)
            x_coord = x_position * self.slot_width

            y_coord = self.flow_y_base

            self.context.node_local_pos[flow_node_id] = (x_coord, y_coord)

            debug_text = f"Y={y_coord:.1f} ← 流程基线{self.flow_y_base:.1f}"
            estimated_height = self.context.get_estimated_node_height(flow_node_id)
            self.context.debug_y_info[flow_node_id] = {
                "type": "flow",
                "text": debug_text,
                "base_y": float(self.flow_y_base),
                "final_y": float(y_coord),
                "node_height": float(estimated_height),
                "node_width": float(self.context.node_width),
                # 新增：块与事件流信息
                "block_index": int(getattr(self.context, "block_order_index", 0)),
                "block_id": str(getattr(self.context, "block_id_string", "")),
                "event_flow_title": getattr(self.context, "event_flow_title", None),
                "event_flow_id": getattr(self.context, "event_flow_id", None),
            }

    def _update_flow_bottom_by_slot(self) -> None:
        """更新每个 X 列上的流程节点底部 Y 坐标，供数据节点计算起始列底。"""
        for flow_node_id in self.context.flow_node_ids:
            x_position = self.node_x_position.get(flow_node_id, 0.0)
            top_y = self.context.node_local_pos[flow_node_id][1]
            estimated_height = self.context.get_estimated_node_height(flow_node_id)
            x_key = int(round(x_position))
            self.context.flow_bottom_by_slot[x_key] = top_y + estimated_height

    # ------------------------------------------------------------------
    # 数据节点坐标分配
    # ------------------------------------------------------------------

    def _assign_data_coordinates(self) -> None:
        """
        分配数据节点坐标（从右到左依次处理）。

        将“坐标决策”与“context 回写/调试记录”解耦：
        1. 使用 `DataCoordinatePlanner` 构造排序候选并生成坐标计划；
        2. 在本方法内统一写入 `context.node_local_pos` 与调试信息。
        """
        planner = DataCoordinatePlanner(self.context, self.node_x_position, self.slot_width)
        placement_plans: list[DataNodePlacementPlan] = planner.plan_data_node_coordinates()

        for plan in placement_plans:
            self.context.node_local_pos[plan.node_id] = (plan.x_coordinate, plan.y_coordinate)
            self._record_data_y_debug_info(plan.node_id, plan.debug_snapshot)

    def _record_data_y_debug_info(self, data_id: str, snapshot: DataNodeYDebugSnapshot) -> None:
        """记录数据节点 Y 分配的调试信息。"""
        final_y = snapshot.final_y
        base_y = snapshot.base_y
        node_height = snapshot.node_height
        strict_column_bottom = snapshot.strict_column_bottom
        start_y_from_above = snapshot.start_y_from_above
        start_y_from_chain_ports = snapshot.start_y_from_chain_ports
        start_y_from_single_target = snapshot.start_y_from_single_target
        start_y_from_multi_targets_mid = snapshot.start_y_from_multi_targets_mid
        forced_by_multi_targets = snapshot.forced_by_multi_targets
        chain_raw_port_y = snapshot.chain_raw_port_y
        chain_port_debug = snapshot.chain_port_debug

        parts = []
        if forced_by_multi_targets and start_y_from_multi_targets_mid is not None:
            parts.append(f"多输出中点{start_y_from_multi_targets_mid:.1f}")
        if start_y_from_above > 0.0:
            parts.append(f"列底{start_y_from_above:.1f}")
        if start_y_from_chain_ports > 0.0:
            parts.append(f"端口{start_y_from_chain_ports:.1f}")
        if start_y_from_single_target is not None:
            parts.append(f"右对齐{start_y_from_single_target:.1f}")
        candidates_text = " / ".join(parts) if parts else "-"

        clamp_note = " + 列底夹紧" if final_y > base_y else ""

        if forced_by_multi_targets:
            debug_text = f"Y={final_y:.1f} ← 多输出中点{start_y_from_multi_targets_mid:.1f}{clamp_note}"
        else:
            if start_y_from_chain_ports > 0.0 and chain_raw_port_y > 0.0:
                debug_text = (
                    f"Y={final_y:.1f} ← max({candidates_text}){clamp_note} "
                    f"[端口Y({'mid' if len(chain_port_debug) > 1 else 'raw'}={chain_raw_port_y:.1f}) "
                    f"+ gap={self.context.input_port_to_data_gap:.1f}]"
                )
            else:
                debug_text = f"Y={final_y:.1f} ← max({candidates_text}){clamp_note}"

        chain_ids_for_node = self.context.data_chain_ids_by_node.get(data_id, [])
        chains_debug: list[dict] = []
        for chain_id in chain_ids_for_node:
            consumer_port_index_raw = self.context.chain_consumer_port_index.get(chain_id)
            consumer_port_index_safe = int(consumer_port_index_raw) if consumer_port_index_raw is not None else None
            chains_debug.append(
                {
                    "id": int(chain_id),
                    "position": int(self.context.node_position_in_chain.get((data_id, chain_id), 0)),
                    "length": int(self.context.chain_length.get(chain_id, 0)),
                    "target_flow": self.context.chain_target_flow.get(chain_id),
                    "is_flow_origin": bool(self.context.chain_is_flow_origin.get(chain_id, False)),
                    "consumer_port_name": self.context.chain_consumer_port_name.get(chain_id),
                    "consumer_port_index": consumer_port_index_safe,
                }
            )

        self.context.debug_y_info[data_id] = {
            "type": "data",
            "text": debug_text,
            "candidates": {
                "column_bottom": float(start_y_from_above),
                "chain_port": float(start_y_from_chain_ports),
                "chain_port_min": float(start_y_from_chain_ports),
                "single_target": float(start_y_from_single_target) if start_y_from_single_target is not None else None,
                "multi_targets_mid": float(start_y_from_multi_targets_mid)
                if start_y_from_multi_targets_mid is not None
                else None,
            },
            "chain_port_raw": float(chain_raw_port_y) if chain_raw_port_y > 0.0 else 0.0,
            "chain_port_gap": float(self.context.input_port_to_data_gap) if start_y_from_chain_ports > 0.0 else 0.0,
            "chain_port_detail": chain_port_debug,
            "node_height": float(node_height),
            "node_width": float(self.context.node_width),
            "final_y": float(final_y),
            "strict_column_bottom": float(strict_column_bottom),
            "was_clamped_by_column_bottom": bool(final_y > base_y),
            "chains": chains_debug,
            # 新增：块与事件流信息
            "block_index": int(getattr(self.context, "block_order_index", 0)),
            "block_id": str(getattr(self.context, "block_id_string", "")),
            "event_flow_title": getattr(self.context, "event_flow_title", None),
            "event_flow_id": getattr(self.context, "event_flow_id", None),
        }

        if getattr(settings, "LAYOUT_DEBUG_PRINT", False):
            header = f"[LAYOUT-Y] 数据节点:{data_id}"
            candidate1 = (
                f"  候选1 列底: {start_y_from_above:.1f}" if start_y_from_above > 0.0 else "  候选1 列底: -"
            )
            if start_y_from_chain_ports > 0.0 and chain_raw_port_y > 0.0:
                ports_desc = ", ".join(
                    [
                        f"(flow={item.get('flow_id')}, idx={item.get('port_index')}, "
                        f"name={item.get('port_name')}, y={item.get('port_y'):.1f})"
                        for item in chain_port_debug
                    ]
                )
                aggregated_label = "mid" if len(chain_port_debug) > 1 else "raw"
                candidate2 = (
                    f"  候选2 端口: {aggregated_label}={chain_raw_port_y:.1f} "
                    f"+ gap={self.context.input_port_to_data_gap:.1f} "
                    f"= {start_y_from_chain_ports:.1f}; 明细: {ports_desc}"
                )
            else:
                candidate2 = "  候选2 端口: -"
            candidate3 = (
                f"  候选3 右对齐: {start_y_from_single_target:.1f}"
                if start_y_from_single_target is not None
                else "  候选3 右对齐: -"
            )
            candidate4 = (
                f"  优先 多输出中点: {start_y_from_multi_targets_mid:.1f}"
                if start_y_from_multi_targets_mid is not None
                else "  优先 多输出中点: -"
            )
            base_line = f"  base_y = max(...) = {base_y:.1f}"
            clamp_line = f"  同列夹紧: 列底={strict_column_bottom:.1f}, 已夹紧={final_y > base_y}"
            final_line = f"  最终 Y = {final_y:.1f}"
            debug(header)
            debug(candidate1)
            debug(candidate2)
            debug(candidate3)
            debug(candidate4)
            debug(base_line)
            debug(clamp_line)
            debug(final_line)


