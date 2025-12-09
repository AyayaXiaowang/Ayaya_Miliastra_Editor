from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any, Set

from engine.graph.models import GraphModel, BasicBlock
from engine.configs.settings import settings
from ..core.layout_algorithm import layout_by_event_regions
from ..core.layout_context import LayoutContext
from ..flow.preprocess import promote_flow_outputs_for_layout
from ..utils.node_copy_utils import collapse_duplicate_data_copies


@dataclass
class LayoutResult:
    """布局输出：纯数据结果，不修改调用方模型。

    - positions: 节点ID → (x, y)
    - basic_blocks: 基本块列表（仅数据结构，用于 UI 半透明显示或编号）
    """

    positions: Dict[str, Tuple[float, float]]
    basic_blocks: List[BasicBlock]
    # 节点ID → 布局Y调试详情（含文本、估算宽/高等）
    y_debug_info: Dict[str, dict] = field(default_factory=dict)
    augmented_model: Optional[GraphModel] = None


class LayoutService:
    """布局服务（纯计算）。

    说明：
    - 输入为 GraphModel（核心数据结构，无 UI 依赖）。
    - 返回 LayoutResult，不直接修改传入模型，便于单元测试与复用。
    - 兼容旧流程：旧的 `layout_by_event_regions(model)` 仍可用于就地修改模型；
      UI 层建议改为调用本服务并将坐标回填至模型与图形项。
    """

    @staticmethod
    def compute_layout(
        model: GraphModel,
        node_library: Optional[Dict[str, Any]] = None,
        include_augmented_model: bool = False,
        clone_model: bool = True,
        write_back_to_input_model: bool = False,
    ) -> LayoutResult:
        """
        Args:
            model: 输入图模型
            node_library: 可选节点库，用于端口类型校正
            include_augmented_model: 是否返回布局后的模型引用
            clone_model: 是否在计算前克隆模型；设为 False 可允许调用方就地更新
            write_back_to_input_model: 当 clone_model=True 时，是否把结果回写到原始模型
        """
        working_model, rename_records = LayoutService._prepare_model_for_layout(
            model,
            node_library,
            clone_model,
        )
        collapse_duplicate_data_copies(working_model)

        layout_by_event_regions(working_model)

        # 可选的布局断言检查（仅在调试模式下启用）
        if getattr(settings, "DEBUG_LAYOUT_ASSERTIONS", False):
            LayoutService._assert_all_data_nodes_assigned(working_model, node_library)

        LayoutService._finalize_layout(
            model,
            working_model,
            clone_model=clone_model,
            rename_records=rename_records,
            write_back_to_input_model=write_back_to_input_model,
        )

        result = LayoutService._build_layout_result(working_model, include_augmented_model)
        return result

    @staticmethod
    def _prepare_model_for_layout(
        model: GraphModel,
        node_library: Optional[Dict[str, Any]],
        clone_model: bool,
    ) -> Tuple[GraphModel, Dict[str, Dict[str, str]]]:
        working_model = model.clone() if clone_model else model
        rename_records: Dict[str, Dict[str, str]] = {}
        if node_library:
            rename_records = promote_flow_outputs_for_layout(working_model, node_library)
        return working_model, rename_records

    @classmethod
    def _finalize_layout(
        cls,
        source_model: GraphModel,
        working_model: GraphModel,
        *,
        clone_model: bool,
        rename_records: Dict[str, Dict[str, str]],
        write_back_to_input_model: bool,
    ) -> None:
        if rename_records and not clone_model:
            cls._revert_promoted_flow_outputs(working_model, rename_records)

        cls._sync_block_relationship_cache(source_model, working_model)

        if clone_model and write_back_to_input_model:
            cls._write_layout_back(source_model, working_model)

    @staticmethod
    def _build_layout_result(
        working_model: GraphModel,
        include_augmented_model: bool,
    ) -> LayoutResult:
        positions: Dict[str, Tuple[float, float]] = {}
        nodes_with_layout = LayoutService._collect_nodes_with_block_positions(working_model.basic_blocks)
        copy_position_overrides: Dict[str, Tuple[Tuple[int, int], Tuple[float, float]]] = {}
        for node_id, node_obj in working_model.nodes.items():
            pos = getattr(node_obj, "pos", (0.0, 0.0)) or (0.0, 0.0)
            if isinstance(pos, (list, tuple)) and len(pos) == 2:
                x_pos, y_pos = pos[0], pos[1]
            else:
                x_pos, y_pos = 0.0, 0.0
            resolved_pos = (float(x_pos), float(y_pos))
            positions[node_id] = resolved_pos
            target_id = LayoutService._resolve_copy_target_id(working_model, node_obj)
            if target_id and target_id not in nodes_with_layout:
                rank = LayoutService._compute_copy_rank(node_obj)
                LayoutService._register_copy_override(copy_position_overrides, target_id, rank, resolved_pos)
        for original_id, (_, override_pos) in copy_position_overrides.items():
            existing_pos = positions.get(original_id)
            if not LayoutService._should_override_original_position(existing_pos):
                continue
            positions[original_id] = override_pos
            if original_id in working_model.nodes:
                working_model.nodes[original_id].pos = override_pos
        basic_blocks: List[BasicBlock] = list(working_model.basic_blocks or [])
        # 调试信息（若存在，原样返回结构化内容）
        existing_debug = getattr(working_model, "_layout_y_debug_info", None)
        if isinstance(existing_debug, dict):
            raw_debug = existing_debug
        else:
            raw_debug = {}
            setattr(working_model, "_layout_y_debug_info", raw_debug)
        y_debug_info: Dict[str, dict] = {}
        copy_debug_overrides: Dict[str, Tuple[Tuple[int, int], dict]] = {}
        for node_id, info in raw_debug.items():
            if isinstance(info, dict):
                info_dict = dict(info)
            else:
                info_dict = {"text": str(info)}
            y_debug_info[node_id] = info_dict
            node_obj = working_model.nodes.get(node_id)
            target_id = LayoutService._resolve_copy_target_id(working_model, node_obj)
            if target_id and target_id not in nodes_with_layout:
                rank = LayoutService._compute_copy_rank(node_obj)
                LayoutService._register_copy_override(copy_debug_overrides, target_id, rank, dict(info_dict))
        debug_map = getattr(working_model, "_layout_y_debug_info", None)
        for original_id, (_, info_dict) in copy_debug_overrides.items():
            y_debug_info[original_id] = info_dict
            if isinstance(debug_map, dict):
                debug_map[original_id] = info_dict

        result = LayoutResult(positions=positions, basic_blocks=basic_blocks, y_debug_info=y_debug_info)
        if include_augmented_model:
            # 将增强后的模型一并返回，供上层进行差异合并（包含副本节点与连线的调整）
            result.augmented_model = working_model
        return result

    @staticmethod
    def _assert_all_data_nodes_assigned(
        model: GraphModel,
        node_library: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        断言所有数据节点都被分配到了某个块。

        仅在调试模式下调用，用于检测布局逻辑中可能遗漏的节点。
        """
        from ..blocks.data_node_ownership import assert_all_data_nodes_assigned

        orphan_ids = assert_all_data_nodes_assigned(model, node_library)
        if orphan_ids:
            raise AssertionError(
                f"布局断言失败：以下数据节点未被分配到任何块：{orphan_ids}"
            )

    @staticmethod
    def _sync_block_relationship_cache(
        original: GraphModel,
        working: GraphModel,
    ) -> None:
        """
        将布局阶段生成的块关系快照同步到外部模型，避免诸如 flow tree 等功能重复运行布局流程。
        """
        if original is working:
            return

        snapshot = getattr(working, "_layout_block_relationships", None)
        block_cache = getattr(working, "_layout_blocks_cache", None)
        layout_context_cache = getattr(working, "_layout_context_cache", None)
        if snapshot is not None:
            setattr(original, "_layout_block_relationships", snapshot)
        if block_cache is not None:
            setattr(original, "_layout_blocks_cache", block_cache)
        if isinstance(layout_context_cache, LayoutContext):
            LayoutService._clone_layout_context_from_source(
                original,
                layout_context_cache,
            )
        debug_info = getattr(working, "_layout_y_debug_info", None)
        if debug_info is not None:
            setattr(original, "_layout_y_debug_info", dict(debug_info))

    @staticmethod
    def _write_layout_back(target: GraphModel, source: GraphModel) -> None:
        """在保持 clone 流程的前提下，将计算结果同步到调用方模型。"""
        nodes_with_layout = LayoutService._collect_nodes_with_block_positions(source.basic_blocks)
        copy_position_overrides: Dict[str, Tuple[Tuple[int, int], Tuple[float, float]]] = {}
        for node_id, node_obj in source.nodes.items():
            pos = getattr(node_obj, "pos", (0.0, 0.0))
            if node_id in target.nodes:
                target.nodes[node_id].pos = (float(pos[0]), float(pos[1])) if pos else (0.0, 0.0)
            target_id = LayoutService._resolve_copy_target_id(source, node_obj)
            if target_id and target_id in target.nodes and target_id not in nodes_with_layout:
                rank = LayoutService._compute_copy_rank(node_obj)
                override_pos = (float(pos[0]), float(pos[1])) if pos else (0.0, 0.0)
                LayoutService._register_copy_override(copy_position_overrides, target_id, rank, override_pos)
        for original_id, (_, override_pos) in copy_position_overrides.items():
            existing_pos = getattr(target.nodes.get(original_id), "pos", None)
            if not LayoutService._should_override_original_position(existing_pos):
                continue
            target.nodes[original_id].pos = override_pos
        target.basic_blocks = list(source.basic_blocks or [])
        debug_info = getattr(source, "_layout_y_debug_info", None)
        if debug_info is not None:
            setattr(target, "_layout_y_debug_info", dict(debug_info))

    @staticmethod
    def _clone_layout_context_from_source(target: GraphModel, source_ctx: LayoutContext) -> None:
        """将克隆模型上的 LayoutContext 重新绑定到目标模型上，避免悬挂引用。"""
        if not isinstance(source_ctx, LayoutContext):
            return
        existing_ctx = getattr(target, "_layout_context_cache", None)
        target_signature = LayoutContext.compute_signature_for_model(target)
        if isinstance(existing_ctx, LayoutContext) and getattr(existing_ctx, "graph_signature", None) == target_signature:
            existing_ctx.set_event_metadata(getattr(source_ctx, "eventMetadataByNode", {}))
            return
        if hasattr(source_ctx, "clone_for_model"):
            cloned_context = source_ctx.clone_for_model(target)
        else:
            cloned_context = LayoutContext(target)
            cloned_context.set_event_metadata(getattr(source_ctx, "eventMetadataByNode", {}))
        setattr(target, "_layout_context_cache", cloned_context)

    @staticmethod
    def _revert_promoted_flow_outputs(
        model: GraphModel,
        rename_records: Dict[str, Dict[str, str]],
    ) -> None:
        """在 clone_model=False 时，将临时提升的端口名恢复为原始命名。"""
        if not rename_records:
            return
        edges_by_src: Dict[str, List[object]] = {}
        for edge in model.edges.values():
            edges_by_src.setdefault(edge.src_node, []).append(edge)
        for node_id, mapping in rename_records.items():
            node = model.nodes.get(node_id)
            if not node:
                continue
            reverted: Dict[str, str] = {}
            for new_name, original_name in mapping.items():
                port = node.get_output_port(new_name)
                if port is None:
                    continue
                port.name = original_name
                reverted[new_name] = original_name
            if reverted:
                node._rebuild_port_maps()
                for edge in edges_by_src.get(node_id, ()):
                    if edge.src_port in reverted:
                        edge.src_port = reverted[edge.src_port]

    @staticmethod
    def _resolve_copy_target_id(model: GraphModel, node_obj: Optional[object]) -> Optional[str]:
        if not node_obj:
            return None
        node_id = getattr(node_obj, "id", "")
        has_copy_suffix = isinstance(node_id, str) and "_copy_block_" in node_id
        is_copy_flag = bool(getattr(node_obj, "is_data_node_copy", False))
        if not (is_copy_flag or has_copy_suffix):
            return None
        original_id = getattr(node_obj, "original_node_id", "") or node_id
        target_id = LayoutService._strip_copy_suffix(original_id)
        if target_id in model.nodes:
            return target_id
        return target_id or None

    @staticmethod
    def _compute_copy_rank(node_obj: object) -> Tuple[int, int]:
        block_id = getattr(node_obj, "copy_block_id", "")
        block_index = LayoutService._parse_block_index(block_id)
        copy_counter = LayoutService._parse_copy_counter(getattr(node_obj, "id", ""))
        return (block_index, copy_counter)

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

    @staticmethod
    def _should_override_original_position(pos: Optional[Tuple[float, float]]) -> bool:
        if not pos:
            return True
        try:
            x_val = float(pos[0])
            y_val = float(pos[1])
        except (TypeError, ValueError, IndexError):
            return True
        threshold = 1e-3
        return abs(x_val) < threshold and abs(y_val) < threshold

    @staticmethod
    def _collect_nodes_with_block_positions(blocks: Optional[List[BasicBlock]]) -> Set[str]:
        node_ids: Set[str] = set()
        if not blocks:
            return node_ids
        for block in blocks:
            if not block:
                continue
            nodes = getattr(block, "nodes", None)
            if not nodes:
                continue
            node_ids.update(nodes)
        return node_ids



