"""
块内数据节点 Y 轴松弛（收敛）规划器。

目标：
- 在不破坏“同列不重叠 + 端口/流程底部安全间距”等硬约束的前提下，
  让存在多父合流/多子分叉的数据节点在垂直方向更接近其邻居的中心位置，
  达到与块间排版相似的“居中”视觉效果。

设计约束：
- 仅调整纯数据节点（由阶段2已放置的数据节点），不调整流程节点的 Y；
- 保持确定性：稳定排序 + 固定迭代轮数上限 + 固定阻尼系数；
- 不引入 try/except；若上下文缺失必要依赖，直接抛错。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set, Tuple

from engine.configs.settings import settings

from ..blocks.block_layout_context import BlockLayoutContext
from .coordinate_assigner_data import DataCoordinatePlanner
from .graph_query_utils import get_node_order_key


@dataclass(frozen=True)
class DataYRelaxationConfig:
    max_rounds: int = 8
    epsilon: float = 0.5
    damping: float = 0.6
    # 当“分叉展开”目标与“邻居对齐”目标冲突时的阈值（像素）
    conflict_threshold: float = 500.0


class DataYRelaxationEngine:
    """块内数据节点 Y 松弛引擎（在已有初值的基础上迭代收敛）。"""

    def __init__(
        self,
        context: BlockLayoutContext,
        node_x_position: Dict[str, float],
        slot_width: float,
        *,
        config: Optional[DataYRelaxationConfig] = None,
    ) -> None:
        self.context = context
        self.node_x_position = dict(node_x_position or {})
        self.slot_width = float(slot_width)
        self.config = config or DataYRelaxationConfig()

    def relax_in_place(self) -> bool:
        """
        在 `context.node_local_pos` 上就地松弛数据节点 Y。

        Returns:
            True 表示发生了实际位置变更；False 表示跳过或未发生变化。
        """
        if not bool(getattr(settings, "LAYOUT_RELAX_DATA_Y_IN_BLOCK", True)):
            return False

        data_node_ids = self._collect_data_nodes_in_scope()
        if len(data_node_ids) < 2:
            return False

        children_map, parents_map = self._build_pure_data_adjacency(data_node_ids)
        data_node_id_set = set(data_node_ids)
        x_key_by_node = {node_id: int(round(self.node_x_position.get(node_id, 0.0))) for node_id in data_node_ids}
        if not self._should_relax(children_map, parents_map, x_key_by_node=x_key_by_node):
            return False

        height_by_node = {node_id: float(self.context.get_estimated_node_height(node_id)) for node_id in data_node_ids}

        # 对每个数据节点计算“不可上移”的硬下界：链条端口/流程底部 + 安全间距（与现有一次性规划一致）。
        planner = DataCoordinatePlanner(self.context, self.node_x_position, self.slot_width)
        lower_bound_by_node = self._build_lower_bounds(data_node_ids, x_key_by_node, planner)

        current_top_y: Dict[str, float] = {node_id: float(self.context.node_local_pos[node_id][1]) for node_id in data_node_ids}

        any_changed = False
        for _ in range(int(self.config.max_rounds)):
            desired_top_y: Dict[str, float] = {}
            # 多父合流的“可行区间”硬约束：目标节点中心必须落在父节点中心的[min, max]区间内。
            # 说明：
            # - 这是块内排版对齐“被连节点应位于父节点之间”的核心约束；
            # - 该约束不会绕开列内不重叠与下界投影：最终仍由 _project_single_column 进行硬投影；
            # - 若后续投影因下界/不重叠导致无法满足该区间，则会以硬约束为准（即出现不可满足时以投影结果为准）。
            multi_parent_bounds_top: Dict[str, Tuple[float, float]] = {}

            # 预计算“分叉父节点 -> 子节点目标 top_y”映射（按端口顺序围绕父节点中心展开）
            split_child_target: Dict[str, float] = {}
            for parent_id, children in children_map.items():
                if len(children) < 2:
                    continue
                parent_center = self._center_y(current_top_y, height_by_node, parent_id)
                total_height = sum(height_by_node[child_id] for child_id in children) + float(self.context.data_stack_gap) * float(
                    len(children) - 1
                )
                group_top = float(parent_center) - float(total_height) * 0.5
                running_top = float(group_top)
                for child_id in children:
                    split_child_target[child_id] = float(running_top)
                    running_top = running_top + height_by_node[child_id] + float(self.context.data_stack_gap)

            # 目标：
            # - 多父合流：贴父中心平均
            # - 多子分叉：贴子中心平均
            # - 其余（含一对一）：贴邻居中心平均（避免“成对边交叉”）
            # - 若同时是“分叉子节点”且存在邻居对齐目标：做折中，必要时优先邻居对齐（强配对）
            for node_id in data_node_ids:
                # 优先使用“入边”补齐父集合，避免仅依赖 out_edges 索引在极端情况下漏算多父关系。
                parents: Set[str] = set(parents_map.get(node_id, set()) or set())
                for edge in self.context.get_in_data_edges(node_id):
                    parent_id = getattr(edge, "src_node", None)
                    if not isinstance(parent_id, str) or parent_id == "":
                        continue
                    if parent_id not in data_node_id_set:
                        continue
                    if parent_id not in current_top_y:
                        continue
                    if not self.context.is_pure_data_node(parent_id):
                        continue
                    parents.add(parent_id)
                children = children_map.get(node_id, [])

                # 强配对：一对一数据边（且跨列）应优先对齐，减少交叉与“回折”走线
                strong_pair = self._is_strong_pairing(
                    node_id,
                    parents_map=parents_map,
                    children_map=children_map,
                    x_key_by_node=x_key_by_node,
                )

                neighbor_centers: List[float] = []
                for parent_id in sorted(parents):
                    if parent_id in current_top_y:
                        neighbor_centers.append(self._center_y(current_top_y, height_by_node, parent_id))
                for child_id in children:
                    if child_id in current_top_y:
                        neighbor_centers.append(self._center_y(current_top_y, height_by_node, child_id))

                neighbor_based_top: Optional[float] = None
                if neighbor_centers:
                    neighbor_based_top = (sum(neighbor_centers) / float(len(neighbor_centers))) - height_by_node[node_id] * 0.5

                if len(parents) >= 2:
                    parent_centers = [
                        self._center_y(current_top_y, height_by_node, pid)
                        for pid in sorted(parents)
                        if pid in current_top_y
                    ]
                    if len(parent_centers) >= 2:
                        avg_center = sum(parent_centers) / float(len(parent_centers))
                        desired_top_y[node_id] = float(avg_center) - height_by_node[node_id] * 0.5
                        # 记录硬区间：目标节点中心需落在父节点中心的[min, max]区间内。
                        # 实现方式：把“中心区间”转换为目标节点 top_y 的可行区间。
                        min_center = float(min(parent_centers))
                        max_center = float(max(parent_centers))
                        half_h = float(height_by_node[node_id]) * 0.5
                        min_top = float(min_center) - half_h
                        max_top = float(max_center) - half_h
                        if min_top <= max_top:
                            multi_parent_bounds_top[node_id] = (float(min_top), float(max_top))
                        else:
                            multi_parent_bounds_top[node_id] = (float(max_top), float(min_top))
                        info = self.context.debug_y_info.get(node_id)
                        if isinstance(info, dict):
                            info["multi_parent_bounds_top"] = {
                                "min": float(min(multi_parent_bounds_top[node_id])),
                                "max": float(max(multi_parent_bounds_top[node_id])),
                            }
                            info["multi_parent_parent_ids"] = sorted(parents)
                    # 多父合流为强约束，仍允许后续与 split_target 折中
                elif len(children) >= 2:
                    child_centers = [self._center_y(current_top_y, height_by_node, cid) for cid in children]
                    avg_center = sum(child_centers) / float(len(child_centers))
                    desired_top_y[node_id] = float(avg_center) - height_by_node[node_id] * 0.5
                    # 多子分叉为强约束，仍允许后续与 split_target 折中
                else:
                    # 默认不对“一对多/多对一”以外的节点施加强吸引，避免把父节点也不必要地拖拽；
                    # 仅在强配对场景下启用邻居对齐（用户最关心的“成对边不交叉”）。
                    if strong_pair and neighbor_based_top is not None:
                        desired_top_y[node_id] = float(neighbor_based_top)

                split_top = split_child_target.get(node_id)
                if split_top is None:
                    continue

                existing = desired_top_y.get(node_id)
                if existing is None:
                    desired_top_y[node_id] = float(split_top)
                    continue

                if strong_pair:
                    # 更偏向邻居对齐（existing 通常为 neighbor_based_top）
                    desired_top_y[node_id] = 0.75 * float(existing) + 0.25 * float(split_top)
                    continue

                conflict_threshold = float(self.config.conflict_threshold)
                if abs(float(existing) - float(split_top)) >= conflict_threshold:
                    # 冲突很大：优先保持分叉紧凑，避免整列被拉出大空洞
                    desired_top_y[node_id] = float(split_top)
                    continue

                # 冲突不大：折中，避免迭代抖动
                desired_top_y[node_id] = 0.5 * float(existing) + 0.5 * float(split_top)

            # 1) 基于目标做阻尼更新，得到“期望 top_y”
            preferred_top_y: Dict[str, float] = {}
            max_delta = 0.0
            damping = float(self.config.damping)
            compact_enabled = bool(getattr(settings, "LAYOUT_COMPACT_DATA_Y_IN_BLOCK", True))
            compact_pull = float(getattr(settings, "LAYOUT_DATA_Y_COMPACT_PULL", 0.6))
            compact_slack_threshold = float(
                getattr(settings, "LAYOUT_DATA_Y_COMPACT_SLACK_THRESHOLD", 200.0)
            )
            if compact_pull < 0.0 or compact_pull > 1.0:
                raise ValueError(
                    f"settings.LAYOUT_DATA_Y_COMPACT_PULL 必须在 [0,1]，当前={compact_pull}"
                )
            if compact_slack_threshold < 0.0:
                raise ValueError(
                    f"settings.LAYOUT_DATA_Y_COMPACT_SLACK_THRESHOLD 必须 >= 0，当前={compact_slack_threshold}"
                )
            for node_id in data_node_ids:
                current = float(current_top_y[node_id])
                target = desired_top_y.get(node_id)
                if target is None:
                    preferred = current
                else:
                    preferred = current + damping * (float(target) - current)

                # 紧凑偏好：在不破坏硬约束的前提下，把“可上移余量很大”的节点往其硬下界靠拢，
                # 以减少整体垂直空洞。硬约束（下界/不重叠/多父区间）仍由后续 _project_all_columns 统一投影保证。
                if compact_enabled:
                    lower_bound = float(lower_bound_by_node.get(node_id, 0.0))
                    slack = float(preferred) - float(lower_bound)
                    if slack > float(compact_slack_threshold):
                        preferred = float(lower_bound) + float(slack) * float(compact_pull)
                preferred_top_y[node_id] = preferred

            # 2) 每列投影到硬约束：下界 + 不重叠（允许上移/下移）
            projected_top_y = self._project_all_columns(
                data_node_ids,
                x_key_by_node=x_key_by_node,
                preferred_top_y=preferred_top_y,
                lower_bound_by_node=lower_bound_by_node,
                height_by_node=height_by_node,
                hard_bounds_top_by_node=multi_parent_bounds_top,
            )

            for node_id, new_top in projected_top_y.items():
                delta = abs(float(new_top) - float(current_top_y[node_id]))
                if delta > max_delta:
                    max_delta = delta
                current_top_y[node_id] = float(new_top)

            if max_delta >= float(self.config.epsilon):
                any_changed = True
                continue

            if max_delta > 0.0:
                any_changed = True
            break

        # 约束收敛收尾：在主体松弛结束后，父节点可能仍会因列内投影发生少量移动，
        # 从而导致个别多父节点略微跑出“父 top_y 区间”。这里做少量轮次的“约束满足投影”，
        # 直到无明显变化或达到上限。
        max_constraint_rounds = 4
        for _ in range(max_constraint_rounds):
            bounds_top: Dict[str, Tuple[float, float]] = {}
            for node_id in data_node_ids:
                parent_ids: Set[str] = set()
                for edge in self.context.get_in_data_edges(node_id):
                    parent_id = getattr(edge, "src_node", None)
                    if not isinstance(parent_id, str) or parent_id == "":
                        continue
                    if parent_id not in data_node_id_set:
                        continue
                    if parent_id not in current_top_y:
                        continue
                    if not self.context.is_pure_data_node(parent_id):
                        continue
                    parent_ids.add(parent_id)
                if len(parent_ids) < 2:
                    continue
                parent_tops = [float(current_top_y[pid]) for pid in sorted(parent_ids) if pid in current_top_y]
                if len(parent_tops) < 2:
                    continue
                min_top = float(min(parent_tops))
                max_top = float(max(parent_tops))
                if min_top <= max_top:
                    bounds_top[node_id] = (float(min_top), float(max_top))
                else:
                    bounds_top[node_id] = (float(max_top), float(min_top))
                info = self.context.debug_y_info.get(node_id)
                if isinstance(info, dict):
                    info["multi_parent_bounds_top"] = {
                        "min": float(min(bounds_top[node_id])),
                        "max": float(max(bounds_top[node_id])),
                    }
                    info["multi_parent_parent_ids"] = sorted(parent_ids)

            if not bounds_top:
                break

            # 先就地夹紧，再投影（保证列内不重叠 + 下界）
            any_violation = False
            for node_id, (min_top, max_top) in bounds_top.items():
                current_val = float(current_top_y.get(node_id, 0.0))
                clamped = current_val
                if current_val < float(min_top):
                    clamped = float(min_top)
                elif current_val > float(max_top):
                    clamped = float(max_top)
                if abs(float(clamped) - float(current_val)) > 1e-9:
                    any_violation = True
                    current_top_y[node_id] = float(clamped)

            projected = self._project_all_columns(
                data_node_ids,
                x_key_by_node=x_key_by_node,
                preferred_top_y=current_top_y,
                lower_bound_by_node=lower_bound_by_node,
                height_by_node=height_by_node,
                hard_bounds_top_by_node=bounds_top,
            )
            max_delta = 0.0
            for node_id, new_top in projected.items():
                old_top = float(current_top_y.get(node_id, 0.0))
                delta = abs(float(new_top) - old_top)
                if delta > max_delta:
                    max_delta = delta
                current_top_y[node_id] = float(new_top)

            if any_violation or max_delta > 1e-9:
                any_changed = True
            if (not any_violation) and max_delta <= float(self.config.epsilon):
                break

        if not any_changed:
            return False

        # 写回坐标（保持 X 不变）
        for node_id in data_node_ids:
            x_coord = float(self.context.node_local_pos[node_id][0])
            y_coord = float(current_top_y[node_id])
            self.context.node_local_pos[node_id] = (x_coord, y_coord)
            self._patch_debug_text_y(node_id, y_coord)

        return True

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _collect_data_nodes_in_scope(self) -> List[str]:
        ordered = list(self.context.data_nodes_in_order or [])
        seen: Set[str] = set()
        result: List[str] = []
        for node_id in ordered:
            if not isinstance(node_id, str) or node_id == "":
                continue
            if node_id in seen:
                continue
            if node_id not in self.context.node_local_pos:
                continue
            if not self.context.is_pure_data_node(node_id):
                continue
            seen.add(node_id)
            result.append(node_id)
        return result

    def _build_pure_data_adjacency(
        self,
        data_node_ids: List[str],
    ) -> Tuple[Dict[str, List[str]], Dict[str, Set[str]]]:
        """构造纯数据子图的父/子关系（仅限本块已放置的数据节点）。"""
        id_set = set(data_node_ids)
        layout_context = self.context.get_port_layout_context()

        children_map: Dict[str, List[str]] = {}
        parents_map: Dict[str, Set[str]] = {node_id: set() for node_id in data_node_ids}

        for src_id in data_node_ids:
            out_edges = self.context.get_data_out_edges(src_id)
            if not out_edges:
                children_map[src_id] = []
                continue

            # 重要：同一对节点之间可能存在多条“数据边”（例如一个节点的多个输出端口连接到
            # 同一个下游节点的多个输入端口）。这不应该被当作“多子分叉”：
            # - 若不去重，会导致 `children` 列表包含大量重复 dst_id；
            # - 从而触发分叉布局与 split_child_target 预排，累计高度会被按“边数量”错误放大，
            #   造成同块内出现巨大 Y 空洞（典型：拆分结构体→拼装结构体这种多端口连接）。
            #
            # 因此这里按 dst_id 去重，仅保留“最靠上”的输出端口顺序（取最小 port_index）作为稳定排序依据。
            best_port_index_by_child: Dict[str, int] = {}
            for edge in out_edges:
                dst_id = getattr(edge, "dst_node", None)
                if not isinstance(dst_id, str) or dst_id == "":
                    continue
                if dst_id not in id_set:
                    continue
                if not self.context.is_pure_data_node(dst_id):
                    continue
                src_port_name = getattr(edge, "src_port", "")
                if layout_context is not None:
                    port_index = int(layout_context.get_output_port_index(src_id, str(src_port_name)))
                else:
                    # 回退：按端口名排序（尽量稳定）
                    port_index = 10**6
                existing = best_port_index_by_child.get(dst_id)
                if existing is None or port_index < int(existing):
                    best_port_index_by_child[dst_id] = int(port_index)
                parents_map.setdefault(dst_id, set()).add(src_id)

            if not best_port_index_by_child:
                children_map[src_id] = []
                continue

            unique_children: List[Tuple[int, str]] = [
                (int(port_index), str(dst_id)) for dst_id, port_index in best_port_index_by_child.items()
            ]
            unique_children.sort(key=lambda pair: (pair[0], pair[1]))
            children_map[src_id] = [dst_id for _, dst_id in unique_children]

        return children_map, parents_map

    def _should_relax(
        self,
        children_map: Dict[str, List[str]],
        parents_map: Dict[str, Set[str]],
        *,
        x_key_by_node: Dict[str, int],
    ) -> bool:
        for node_id, parents in parents_map.items():
            if len(parents) >= 2:
                return True
            children = children_map.get(node_id, [])
            if len(children) >= 2:
                return True
            if len(parents) == 1:
                parent_id = next(iter(parents))
                siblings = children_map.get(parent_id, [])
                if len(siblings) >= 2:
                    return True
            # 一对一且跨列：也值得做少量松弛（典型诉求：成对边避免交叉）
            if self._is_strong_pairing(
                node_id,
                parents_map=parents_map,
                children_map=children_map,
                x_key_by_node=x_key_by_node,
            ):
                return True
        return False

    def _is_strong_pairing(
        self,
        node_id: str,
        *,
        parents_map: Dict[str, Set[str]],
        children_map: Dict[str, List[str]],
        x_key_by_node: Dict[str, int],
    ) -> bool:
        """
        判断某节点是否处于“强配对”的一对一关系中：
        - 本节点只有 1 个纯数据子节点
        - 子节点只有 1 个纯数据父节点
        - 且二者列不同（跨列），此时对齐能显著减少交叉与回折
        """
        children = children_map.get(node_id, [])
        if len(children) != 1:
            return False
        child_id = children[0]
        parents_of_child = parents_map.get(child_id, set())
        if len(parents_of_child) != 1:
            return False
        if int(x_key_by_node.get(node_id, 0)) == int(x_key_by_node.get(child_id, 0)):
            return False
        return True

    def _build_lower_bounds(
        self,
        data_node_ids: List[str],
        x_key_by_node: Dict[str, int],
        planner: DataCoordinatePlanner,
    ) -> Dict[str, float]:
        result: Dict[str, float] = {}
        for node_id in data_node_ids:
            x_key = int(x_key_by_node.get(node_id, 0))
            flow_bottom = float(self.context.flow_bottom_by_slot.get(x_key, 0.0))
            column_min = flow_bottom + float(self.context.flow_to_data_gap)
            # 链条端口下界（若无链信息，则内部会回退到列底 + gap）
            chain_min = float(planner._get_min_chain_port_y(node_id))  # noqa: SLF001
            result[node_id] = max(0.0, column_min, chain_min)
        return result

    @staticmethod
    def _center_y(current_top_y: Dict[str, float], height_by_node: Dict[str, float], node_id: str) -> float:
        return float(current_top_y[node_id]) + float(height_by_node[node_id]) * 0.5

    def _project_all_columns(
        self,
        data_node_ids: List[str],
        *,
        x_key_by_node: Dict[str, int],
        preferred_top_y: Dict[str, float],
        lower_bound_by_node: Dict[str, float],
        height_by_node: Dict[str, float],
        hard_bounds_top_by_node: Optional[Dict[str, Tuple[float, float]]] = None,
    ) -> Dict[str, float]:
        # 分桶：列键 -> 节点列表
        column_map: Dict[int, List[str]] = {}
        for node_id in data_node_ids:
            column_map.setdefault(int(x_key_by_node.get(node_id, 0)), []).append(node_id)

        projected: Dict[str, float] = {}
        for col_key, node_list in column_map.items():
            projected.update(
                self._project_single_column(
                    node_list,
                    preferred_top_y=preferred_top_y,
                    lower_bound_by_node=lower_bound_by_node,
                    height_by_node=height_by_node,
                    hard_bounds_top_by_node=hard_bounds_top_by_node,
                )
            )
        return projected

    def _project_single_column(
        self,
        node_ids: Iterable[str],
        *,
        preferred_top_y: Dict[str, float],
        lower_bound_by_node: Dict[str, float],
        height_by_node: Dict[str, float],
        hard_bounds_top_by_node: Optional[Dict[str, Tuple[float, float]]] = None,
    ) -> Dict[str, float]:
        # 列内稳定顺序（关键约束）：
        # - 先按“链 ID（升序）”固定同列的链优先级顺序，保证 chain_id 越大越靠下；
        # - 再按上游阶段生成的 node_stack_order 保持链内/分叉堆叠提示；
        # - 最后才使用 preferred_y（松弛目标）与源码行号/ID 做稳定兜底。
        #
        # 说明：
        # - 初次放置阶段已经按链 ID 给出了同列的上下顺序；松弛阶段若按 preferred_y 重新排序，
        #   会导致同列节点“换位”，从而违背用户的链序预期。
        node_list = list(node_ids)

        def sort_key(node_id: str) -> tuple[int, int, int, float, tuple[int, str]]:
            chain_ids = self.context.data_chain_ids_by_node.get(node_id) or []
            if chain_ids:
                chain_bucket = 0
                chain_key = int(min(chain_ids))
            else:
                chain_bucket = 1
                chain_key = 10**9

            stack_hint = int(self.context.node_stack_order.get(node_id, 10**9))
            node_obj = self.context.model.nodes.get(node_id)
            stable_key = get_node_order_key(node_obj) if node_obj is not None else (10**9, node_id)
            return (
                chain_bucket,
                chain_key,
                stack_hint,
                float(preferred_top_y.get(node_id, 0.0)),
                stable_key,
            )

        node_list.sort(key=sort_key)

        gap = float(self.context.data_stack_gap)

        # 前向投影：满足下界与不重叠
        forward_y: List[float] = []
        for index, node_id in enumerate(node_list):
            lb = float(lower_bound_by_node.get(node_id, 0.0))
            preferred = float(preferred_top_y.get(node_id, 0.0))
            hard_min_top = None
            hard_max_top = None
            if hard_bounds_top_by_node is not None:
                bounds = hard_bounds_top_by_node.get(node_id)
                if bounds is not None:
                    hard_min_top, hard_max_top = bounds
                    if hard_min_top > hard_max_top:
                        hard_min_top, hard_max_top = hard_max_top, hard_min_top
                    lb = max(lb, float(hard_min_top))
            if index == 0:
                y_val = max(lb, preferred)
            else:
                prev_id = node_list[index - 1]
                prev_top = float(forward_y[index - 1])
                prev_h = float(height_by_node.get(prev_id, 0.0))
                y_val = max(lb, preferred, prev_top + prev_h + gap)
            forward_y.append(float(y_val))

        # 反向投影：允许上移（但不越过下界），减少“全列只会往下挤”的副作用
        backward_y = list(forward_y)
        for index in range(len(node_list) - 2, -1, -1):
            node_id = node_list[index]
            next_id = node_list[index + 1]
            next_top = float(backward_y[index + 1])
            max_allowed = next_top - float(height_by_node.get(node_id, 0.0)) - gap
            lb = float(lower_bound_by_node.get(node_id, 0.0))
            hard_min_top = None
            hard_max_top = None
            if hard_bounds_top_by_node is not None:
                bounds = hard_bounds_top_by_node.get(node_id)
                if bounds is not None:
                    hard_min_top, hard_max_top = bounds
                    if hard_min_top > hard_max_top:
                        hard_min_top, hard_max_top = hard_max_top, hard_min_top
                    lb = max(lb, float(hard_min_top))
                    max_allowed = min(float(max_allowed), float(hard_max_top))
            # 允许上移到 max_allowed，但不突破下界；保持尽量靠近 forward 的结果，避免剧烈回跳
            backward_y[index] = max(lb, min(float(backward_y[index]), float(max_allowed)))

        return {node_id: float(y_val) for node_id, y_val in zip(node_list, backward_y)}

    def _patch_debug_text_y(self, node_id: str, new_y: float) -> None:
        info = self.context.debug_y_info.get(node_id)
        if not isinstance(info, dict):
            return
        info["final_y"] = float(new_y)
        text = info.get("text")
        if not isinstance(text, str) or not text.startswith("Y="):
            return
        head, sep, tail = text.partition(" ")
        # head: "Y=123.4"
        if sep == "":
            info["text"] = f"Y={float(new_y):.1f}"
        else:
            info["text"] = f"Y={float(new_y):.1f} {tail}"


