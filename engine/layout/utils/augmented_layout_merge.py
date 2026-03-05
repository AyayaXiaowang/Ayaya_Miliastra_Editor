from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Set, Tuple, Any

from engine.graph.models import GraphModel
from engine.layout.internal.layout_service import LayoutResult
from engine.layout.utils.copy_identity_utils import is_data_node_copy


@dataclass
class AugmentedLayoutMergeDelta:
    """增强布局差分合并结果（仅描述模型层变更，不涉及 UI 场景）。"""

    added_node_ids: Set[str] = field(default_factory=set)
    added_edge_ids: Set[str] = field(default_factory=set)
    removed_edge_ids: Set[str] = field(default_factory=set)
    removed_copy_node_ids: Set[str] = field(default_factory=set)

    used_augmented_model: bool = False
    used_fallback_without_augmented: bool = False
    touched_edges_revision: bool = False


def apply_augmented_layout_merge(
    target_model: GraphModel,
    layout_result: LayoutResult,
    *,
    augmented_model: Optional[GraphModel] = None,
    allow_fallback_without_augmented: bool = False,
) -> AugmentedLayoutMergeDelta:
    """将 LayoutService 的增强布局结果以“差分合并”方式应用到目标模型。

    语义约束（保持与历史行为一致）：
    - 只合并增强模型中新出现的节点/边（典型场景：跨块复制产生的数据副本节点与其连线）
    - 只删除“增强模型中已被清理”的旧边（典型场景：跨块旧边被副本边替换/去重）
    - 仅删除“增强模型中已被清理”的孤立副本节点（只对 data_copy 生效，避免误删用户节点）
    - 坐标/基本块/调试信息以增强模型为准回填到 target_model

    Args:
        target_model: 需要被更新的模型（原模型，会被原地修改）
        layout_result: LayoutService.compute_layout 的返回值
        augmented_model: 可显式指定增强模型（默认取 layout_result.augmented_model）
        allow_fallback_without_augmented:
            当增强模型不可用时，是否退化为仅按 layout_result.positions/basic_blocks/y_debug_info 回填。
            - True：用于资源加载等“尽力而为”的场景
            - False：用于 UI 自动排版等希望严格依赖增强模型的场景（保持历史行为：直接不处理）
    """

    resolved_augmented_model = augmented_model if augmented_model is not None else getattr(layout_result, "augmented_model", None)
    merge_delta = AugmentedLayoutMergeDelta()

    if resolved_augmented_model is None:
        if not allow_fallback_without_augmented:
            return merge_delta

        merge_delta.used_fallback_without_augmented = True
        positions = getattr(layout_result, "positions", None) or {}
        for node_id, raw_pos in positions.items():
            node_obj = target_model.nodes.get(node_id)
            if node_obj is None:
                continue
            normalized_pos = _normalize_pos(raw_pos)
            node_obj.pos = normalized_pos

        target_model.basic_blocks = list(getattr(layout_result, "basic_blocks", None) or [])
        debug_info = getattr(layout_result, "y_debug_info", None) or {}
        if debug_info:
            setattr(target_model, "_layout_y_debug_info", dict(debug_info))
        return merge_delta

    merge_delta.used_augmented_model = True

    model_node_ids_before = set(target_model.nodes.keys())
    model_edge_ids_before = set(target_model.edges.keys())
    augmented_node_ids = set(resolved_augmented_model.nodes.keys())
    augmented_edge_ids = set(resolved_augmented_model.edges.keys())

    # 1) 合并新增节点（跨块复制产生的数据副本等）
    nodes_to_add = sorted(augmented_node_ids - model_node_ids_before)
    for node_id in nodes_to_add:
        target_model.nodes[node_id] = resolved_augmented_model.nodes[node_id]
        merge_delta.added_node_ids.add(node_id)

    # 2) 合并新增连线（副本边、去重后的新边等）
    edges_to_add = sorted(augmented_edge_ids - model_edge_ids_before)
    for edge_id in edges_to_add:
        target_model.edges[edge_id] = resolved_augmented_model.edges[edge_id]
        merge_delta.added_edge_ids.add(edge_id)

    edges_modified = False

    # 3) 删除增强模型中已被移除的旧连线（例如跨块旧边被副本边替换）
    edges_to_remove = sorted(model_edge_ids_before - augmented_edge_ids)
    for edge_id in edges_to_remove:
        if edge_id in target_model.edges:
            target_model.edges.pop(edge_id, None)
            merge_delta.removed_edge_ids.add(edge_id)
            edges_modified = True

    # 4) 删除增强模型中被清理掉的孤立副本节点（仅删除 data_copy，避免误删用户节点）
    nodes_to_remove = sorted(model_node_ids_before - augmented_node_ids)
    for node_id in nodes_to_remove:
        node_obj = target_model.nodes.get(node_id)
        if node_obj is None:
            continue
        if not is_data_node_copy(node_obj):
            continue

        # 先移除与该副本节点关联的边（兼容“边集合未完全同步”的历史边缘场景）
        related_edge_ids = [
            edge_id
            for edge_id, edge_obj in target_model.edges.items()
            if getattr(edge_obj, "src_node", None) == node_id or getattr(edge_obj, "dst_node", None) == node_id
        ]
        if related_edge_ids:
            edges_modified = True
        for edge_id in related_edge_ids:
            if edge_id in target_model.edges:
                target_model.edges.pop(edge_id, None)
                merge_delta.removed_edge_ids.add(edge_id)

        target_model.nodes.pop(node_id, None)
        merge_delta.removed_copy_node_ids.add(node_id)

    # 5) 回填坐标：以增强模型坐标为准，保证最终位置与自动排版一致
    for node_id, augmented_node_obj in resolved_augmented_model.nodes.items():
        node_obj = target_model.nodes.get(node_id)
        if node_obj is None:
            continue
        raw_pos = getattr(augmented_node_obj, "pos", None)
        node_obj.pos = _normalize_pos(raw_pos)

    # 6) 回填基本块与布局调试信息（优先 result.basic_blocks，回退 augmented.basic_blocks）
    basic_blocks = list(getattr(layout_result, "basic_blocks", None) or getattr(resolved_augmented_model, "basic_blocks", None) or [])
    target_model.basic_blocks = basic_blocks

    debug_info_augmented = getattr(resolved_augmented_model, "_layout_y_debug_info", None) or {}
    if debug_info_augmented:
        setattr(target_model, "_layout_y_debug_info", dict(debug_info_augmented))

    # 6.5) 同步增强布局写入的“端口类型覆盖”（port_type_overrides）。
    # 说明：
    # - 长连线中转（获取局部变量 relay）等增强流程会在 augmented_model 上更新 metadata.port_type_overrides；
    # - 若差分合并不同步该字段，会导致 UI/工具侧的有效类型推断与后续结构校验口径漂移。
    target_meta = getattr(target_model, "metadata", None) or {}
    if not isinstance(target_meta, dict):
        target_meta = {}
    augmented_meta = getattr(resolved_augmented_model, "metadata", None) or {}
    augmented_overrides = augmented_meta.get("port_type_overrides") if isinstance(augmented_meta, dict) else None
    if isinstance(augmented_overrides, dict):
        # 仅做浅层规范化拷贝：{node_id: {port_name: type_text}}
        copied: dict[str, dict[str, str]] = {}
        for node_id, mapping in augmented_overrides.items():
            if not isinstance(node_id, str) or not isinstance(mapping, dict):
                continue
            copied[node_id] = {str(p): str(t) for p, t in mapping.items() if isinstance(p, str)}
        target_meta["port_type_overrides"] = copied
    else:
        target_meta.pop("port_type_overrides", None)
    target_model.metadata = target_meta
    # 清理缓存（port_type_effective_resolver.build_port_type_overrides 会缓存该字段）
    setattr(target_model, "_effective_port_type_overrides_cache", None)

    # 7) 触发 edges_revision：差分合并直接操作 dict，需显式让依赖 edges 的缓存失效
    if merge_delta.added_edge_ids or merge_delta.removed_edge_ids or edges_modified:
        target_model.touch_edges_revision()
        merge_delta.touched_edges_revision = True

    return merge_delta


def _normalize_pos(raw_pos: Any) -> Tuple[float, float]:
    if isinstance(raw_pos, (list, tuple)) and len(raw_pos) >= 2:
        x_value = raw_pos[0]
        y_value = raw_pos[1]
        x_pos = float(x_value) if x_value is not None else 0.0
        y_pos = float(y_value) if y_value is not None else 0.0
        return (x_pos, y_pos)
    return (0.0, 0.0)


