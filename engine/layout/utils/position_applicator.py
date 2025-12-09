"""
位置应用器

负责将布局计算的结果应用到图模型中，包括：
- 计算块的稳定顺序
- 应用节点坐标
- 转换为BasicBlock并保存
- 处理布局调试信息
"""

from __future__ import annotations
from typing import List, Dict, TYPE_CHECKING, Tuple, Any, Optional, Set

from ..core.layout_models import LayoutBlock
from ..utils.basic_block_utils import build_basic_block

if TYPE_CHECKING:
    from engine.graph.models import GraphModel


class PositionApplicator:
    """位置应用器"""

    def __init__(self, model: GraphModel, layout_blocks: List["LayoutBlock"]):
        self.model = model
        self.layout_blocks = layout_blocks

    def apply_positions(self) -> None:
        """应用最终位置到所有节点"""
        # 计算稳定的块顺序（复用缓存的块图）
        ordered_layout_blocks = self._compute_stable_block_order()

        applied_node_ids: Set[str] = set()

        # 应用节点位置
        for layout_block in ordered_layout_blocks:
            block_left_x, block_top_y = layout_block.top_left_pos
            for node_id, (local_x, local_y) in layout_block.node_local_pos.items():
                if node_id in self.model.nodes:
                    self.model.nodes[node_id].pos = (block_left_x + local_x, block_top_y + local_y)
                    applied_node_ids.add(node_id)

        # 同步缺失坐标的原始节点（仅当其未在任何块中获得位置时）
        self._propagate_copy_positions(applied_node_ids)

        # 转换为BasicBlock并保存
        self._convert_and_save_basic_blocks(ordered_layout_blocks)

        # 处理布局调试信息
        self._process_debug_info(ordered_layout_blocks)

    def _compute_stable_block_order(self) -> List["LayoutBlock"]:
        """计算稳定的块顺序（复用缓存的块图）"""
        # 强制要求所有块在分块阶段即分配了稳定序号
        if not all(getattr(block, "order_index", 0) > 0 for block in self.layout_blocks):
            raise ValueError("All layout blocks must have an order_index assigned during identification.")
        return sorted(self.layout_blocks, key=lambda block: block.order_index)

    def _convert_and_save_basic_blocks(self, ordered_layout_blocks: List["LayoutBlock"]) -> None:
        """转换为BasicBlock并保存到模型

        注意：这里需要根据副本节点的 copy_block_id 精确归属到对应块，避免同一个数据副本
        被多个 BasicBlock 同时引用，从而在 UI 中表现为“同一节点出现在多个块内”。
        """
        basic_blocks = []
        for layout_block in ordered_layout_blocks:
            # 按块过滤可见的数据节点：
            # - 普通节点：始终归入所在块
            # - 副本节点：仅当 copy_block_id / ID 后缀与当前块 order_index 匹配时保留
            effective_data_nodes: List[str] = []
            for node_id in layout_block.data_nodes:
                node_obj = self.model.nodes.get(node_id)
                if not node_obj:
                    continue

                is_copy = bool(getattr(node_obj, "is_data_node_copy", False))
                if is_copy:
                    copy_block_id = getattr(node_obj, "copy_block_id", "") or ""
                    expected_index = self._parse_block_index(copy_block_id)

                    # 若 copy_block_id 无法解析（返回哨兵值），则尝试从 ID 后缀 `_copy_block_{idx}_...` 推断
                    if expected_index >= 10**6 and isinstance(node_id, str) and "_copy_block_" in node_id:
                        suffix = node_id.rsplit("_copy_block_", 1)[-1]
                        parts = suffix.split("_")
                        if parts and parts[0].isdigit():
                            expected_index = int(parts[0])

                    current_index = getattr(layout_block, "order_index", 0)
                    # 仅当副本的目标块索引与当前块一致时才纳入本 BasicBlock
                    if 0 < expected_index < 10**6 and expected_index != current_index:
                        continue

                effective_data_nodes.append(node_id)

            # 将过滤后的数据节点写回 LayoutBlock，保持后续调试逻辑一致
            layout_block.data_nodes = list(effective_data_nodes)

            basic_block = build_basic_block(
                node_ids=layout_block.flow_nodes + effective_data_nodes,
                color=layout_block.color,
            )
            basic_blocks.append(basic_block)

        self.model.basic_blocks = basic_blocks

    def _process_debug_info(self, ordered_layout_blocks: List["LayoutBlock"]) -> None:
        """处理布局Y调试信息（将块内局部Y转换为全局Y）"""
        debug_map = getattr(self.model, "_layout_y_debug_info", None)
        if not isinstance(debug_map, dict) or not debug_map:
            return

        # 为每个块内节点的调试条目增加其块顶偏移量（仅Y向）
        for layout_block in ordered_layout_blocks:
            block_top_y = float(layout_block.top_left_pos[1])
            # 该块内的所有节点（含数据与流程）
            local_ids = set(layout_block.node_local_pos.keys())
            for node_id in local_ids:
                info = debug_map.get(node_id)
                if not isinstance(info, Dict):
                    continue
                info_type = info.get("type")

                # 通用字段转换
                if "final_y" in info:
                    info["final_y"] = float(info["final_y"]) + block_top_y

                # 候选字段（数据节点）
                if "candidates" in info and isinstance(info["candidates"], Dict):
                    candidates = info["candidates"]
                    if "column_bottom" in candidates and candidates["column_bottom"] is not None:
                        candidates["column_bottom"] = float(candidates["column_bottom"]) + block_top_y
                    if "chain_port" in candidates and candidates["chain_port"] is not None:
                        candidates["chain_port"] = float(candidates["chain_port"]) + block_top_y
                    if "chain_port_min" in candidates and candidates["chain_port_min"] is not None:
                        candidates["chain_port_min"] = float(candidates["chain_port_min"]) + block_top_y
                    if "single_target" in candidates and candidates["single_target"] is not None:
                        candidates["single_target"] = float(candidates["single_target"]) + block_top_y

                # 数据节点专有细节
                if info_type == "data":
                    if "strict_column_bottom" in info:
                        info["strict_column_bottom"] = float(info["strict_column_bottom"]) + block_top_y
                    if "chain_port_raw" in info and float(info.get("chain_port_raw", 0.0)) > 0.0:
                        info["chain_port_raw"] = float(info["chain_port_raw"]) + block_top_y

                # 流程节点专有：基线
                if info_type == "flow":
                    if "base_y" in info:
                        info["base_y"] = float(info["base_y"]) + block_top_y

                # 重建text（使用全局Y数值）
                self._rebuild_debug_text(info, info_type)

    def _rebuild_debug_text(self, info: dict, info_type: Optional[str]) -> None:
        """重建调试文本"""
        if info_type == "flow":
            base_y_val = float(info.get("base_y", 0.0))
            final_y_val = float(info.get("final_y", 0.0))
            shift_down_val = float(info.get("shift_down", 0.0)) if "shift_down" in info else 0.0
            shift_text = f" + 下移{shift_down_val:.1f}" if shift_down_val > 0.0 else ""
            info["text"] = f"Y={final_y_val:.1f} ← 流程基线{base_y_val:.1f}{shift_text}"
        elif info_type == "data":
            candidates = info.get("candidates", {})
            parts: list[str] = []
            column_bottom = candidates.get("column_bottom", 0.0) or 0.0
            chain_port = candidates.get("chain_port", 0.0) or 0.0
            single_target = candidates.get("single_target")
            if column_bottom > 0.0:
                parts.append(f"列底{column_bottom:.1f}")
            if chain_port > 0.0:
                parts.append(f"端口{chain_port:.1f}")
            if single_target is not None:
                parts.append(f"右对齐{float(single_target):.1f}")
            candidates_text = " / ".join(parts) if parts else "-"
            final_y_val = float(info.get("final_y", 0.0))
            was_clamped = bool(info.get("was_clamped_by_column_bottom", False))
            clamp_note = " + 列底夹紧" if was_clamped else ""
            # 如有原始端口Y与gap，附加拆解说明
            if float(info.get("chain_port_raw", 0.0)) > 0.0 and float(info.get("chain_port_gap", 0.0)) > 0.0:
                port_raw = float(info["chain_port_raw"])
                gap_val = float(info["chain_port_gap"])
                info["text"] = (
                    f"Y={final_y_val:.1f} ← max({candidates_text}){clamp_note} "
                    f"[端口Y={port_raw:.1f} + gap={gap_val:.1f}]"
                )
            else:
                info["text"] = f"Y={final_y_val:.1f} ← max({candidates_text}){clamp_note}"

    # ---------------- 副本坐标/调试同步 ----------------
    def _propagate_copy_positions(self, applied_node_ids: Set[str]) -> None:
        """将副本节点的坐标与调试信息同步回尚未拥有位置的原始节点。"""
        copy_position_overrides: Dict[str, Tuple[Tuple[int, int], Tuple[float, float]]] = {}
        copy_debug_overrides: Dict[str, Tuple[Tuple[int, int], Dict[str, Any]]] = {}
        debug_map = getattr(self.model, "_layout_y_debug_info", None)

        for node in self.model.nodes.values():
            target_id = self._resolve_copy_target_id(node)
            if not target_id or target_id in applied_node_ids:
                continue
            rank = self._compute_copy_rank(node)
            resolved_pos = self._normalize_pos(getattr(node, "pos", None))
            if resolved_pos is not None:
                self._register_copy_override(copy_position_overrides, target_id, rank, resolved_pos)
            if isinstance(debug_map, dict):
                info = debug_map.get(node.id)
                if isinstance(info, dict):
                    self._register_copy_override(copy_debug_overrides, target_id, rank, dict(info))

        for target_id, (_, pos) in copy_position_overrides.items():
            if target_id in self.model.nodes:
                self.model.nodes[target_id].pos = pos

        # 调试信息仅合并链路信息，保留原块内的基础数值（final_y / base_y 等）
        if isinstance(debug_map, dict):
            for target_id, (_, info_dict) in copy_debug_overrides.items():
                existing = debug_map.get(target_id)
                if not isinstance(existing, Dict):
                    debug_map[target_id] = info_dict
                    continue

                existing_chains = existing.get("chains")
                new_chains = info_dict.get("chains")
                if isinstance(existing_chains, list) or isinstance(new_chains, list):
                    merged: list[Any] = []
                    if isinstance(existing_chains, list):
                        merged.extend(existing_chains)
                    if isinstance(new_chains, list):
                        for item in new_chains:
                            if item not in merged:
                                merged.append(item)
                    existing["chains"] = merged

                debug_map[target_id] = existing

    @staticmethod
    def _normalize_pos(pos: Any) -> Optional[Tuple[float, float]]:
        if isinstance(pos, (tuple, list)) and len(pos) == 2:
            return float(pos[0]), float(pos[1])
        return None

    @staticmethod
    def _register_copy_override(
        overrides: Dict[str, Tuple[Tuple[int, int], Any]],
        original_id: str,
        rank: Tuple[int, int],
        payload: Any,
    ) -> None:
        existing = overrides.get(original_id)
        if existing is None or rank < existing[0]:
            overrides[original_id] = (rank, payload)

    @staticmethod
    def _compute_copy_rank(node_obj: Any) -> Tuple[int, int]:
        block_id = getattr(node_obj, "copy_block_id", "")
        block_index = PositionApplicator._parse_block_index(block_id)
        copy_counter = PositionApplicator._parse_copy_counter(getattr(node_obj, "id", ""))
        return (block_index, copy_counter)

    @staticmethod
    def _parse_block_index(block_id: str) -> int:
        if isinstance(block_id, str) and block_id.startswith("block_"):
            suffix = block_id.split("_", 1)[-1]
            if suffix.isdigit():
                return int(suffix)
        return 10**6

    @staticmethod
    def _parse_copy_counter(node_id: str) -> int:
        if "_copy_" not in node_id:
            return 10**6
        suffix = node_id.rsplit("_copy_", 1)[-1]
        parts = suffix.split("_")
        for part in reversed(parts):
            if part.isdigit():
                return int(part)
        return 10**6

    def _resolve_copy_target_id(self, node_obj: Any) -> Optional[str]:
        if not node_obj:
            return None
        node_id = getattr(node_obj, "id", "")
        has_copy_suffix = isinstance(node_id, str) and "_copy_block_" in node_id
        is_copy_flag = bool(getattr(node_obj, "is_data_node_copy", False))
        if not (has_copy_suffix or is_copy_flag):
            return None
        original_id = getattr(node_obj, "original_node_id", "") or node_id
        target_id = PositionApplicator._strip_copy_suffix(original_id)
        if target_id and target_id in self.model.nodes:
            return target_id
        return None

    @staticmethod
    def _strip_copy_suffix(node_id: str) -> str:
        marker = "_copy_block_"
        result = node_id
        while True:
            idx = result.rfind(marker)
            if idx == -1:
                break
            result = result[:idx]
        return result



