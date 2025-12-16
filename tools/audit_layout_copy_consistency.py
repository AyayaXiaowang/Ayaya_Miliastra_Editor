"""
布局跨块复制一致性审计工具

用途：
- 从节点图 Python 源文件解析 GraphModel；
- 通过 LayoutService 执行一次完整布局（含跨块复制与副本处理）；
- 对增强模型中的“数据节点副本归属 / LayoutBlock 归属 / 幂等性”做结构化审计；
- 若发现异常，退出码为 1，并打印可定位的错误信息。

用法（在项目根目录执行）：
  python -X utf8 -m tools.audit_layout_copy_consistency <graph_py_path>
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple


if __package__:
    from ._bootstrap import ensure_workspace_root_on_sys_path
else:
    from _bootstrap import ensure_workspace_root_on_sys_path

WORKSPACE = ensure_workspace_root_on_sys_path()


from engine.configs.settings import settings  # noqa: E402
from engine.graph.graph_code_parser import GraphCodeParser  # noqa: E402
from engine.layout import LayoutService  # noqa: E402
from engine.layout.internal.layout_context import LayoutContext  # noqa: E402
from engine.layout.utils.copy_identity_utils import (  # noqa: E402
    infer_copy_block_id_from_node_id,
    is_data_node_copy,
    resolve_copy_block_id,
    resolve_canonical_original_id,
)
from engine.layout.utils.global_copy_manager import GlobalCopyManager  # noqa: E402
from engine.nodes.node_registry import get_node_registry  # noqa: E402


def _resolve_code_path(arg: str) -> Path:
    candidate = Path(arg)
    if not candidate.is_absolute():
        candidate = WORKSPACE / candidate
    return candidate


def _collect_layout_blocks_cache(augmented_model: Any) -> List[Any]:
    cache = getattr(augmented_model, "_layout_blocks_cache", None)
    if isinstance(cache, list):
        return cache
    return []


def _build_block_id_by_flow_node(layout_blocks: List[Any]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for block in layout_blocks:
        order_index = int(getattr(block, "order_index", 0) or 0)
        block_id = f"block_{order_index}"
        flow_nodes = list(getattr(block, "flow_nodes", []) or [])
        for node_id in flow_nodes:
            if isinstance(node_id, str) and node_id:
                mapping[node_id] = block_id
    return mapping


def _build_block_lookup(layout_blocks: List[Any]) -> Dict[str, Any]:
    lookup: Dict[str, Any] = {}
    for block in layout_blocks:
        order_index = int(getattr(block, "order_index", 0) or 0)
        block_id = f"block_{order_index}"
        lookup[block_id] = block
    return lookup


def _snapshot_copy_nodes(model: Any) -> Set[str]:
    result: Set[str] = set()
    nodes = getattr(model, "nodes", None)
    if not isinstance(nodes, dict):
        return result
    for node_id, node_obj in nodes.items():
        if not isinstance(node_id, str) or not node_id:
            continue
        if is_data_node_copy(node_obj):
            result.add(node_id)
    return result


def _assert_copy_block_membership_consistent(
    augmented_model: Any,
    layout_blocks: List[Any],
) -> List[str]:
    """校验：副本节点只归属于其 copy_block_id 对应的 LayoutBlock。"""
    errors: List[str] = []
    nodes = getattr(augmented_model, "nodes", None)
    if not isinstance(nodes, dict):
        return ["augmented_model.nodes 不是 dict，无法审计"]

    block_by_id = _build_block_lookup(layout_blocks)

    # 1) LayoutBlock 内部一致性：copy node 必须匹配 block.order_index
    for block in layout_blocks:
        order_index = int(getattr(block, "order_index", 0) or 0)
        expected_block_id = f"block_{order_index}"
        data_nodes = list(getattr(block, "data_nodes", []) or [])
        for node_id in data_nodes:
            if not isinstance(node_id, str) or not node_id:
                continue
            node_obj = nodes.get(node_id)
            if node_obj is None:
                continue
            if not is_data_node_copy(node_obj):
                continue
            actual_block_id = resolve_copy_block_id(node_obj) or infer_copy_block_id_from_node_id(node_id)
            if actual_block_id and actual_block_id != expected_block_id:
                errors.append(
                    f"LayoutBlock({expected_block_id}) 内包含副本 {node_id}，但其 copy_block_id={actual_block_id}"
                )

    # 2) 全局反查：每个副本都应该出现在其目标块的 LayoutBlock.data_nodes 中
    for node_id, node_obj in nodes.items():
        if not isinstance(node_id, str) or not node_id:
            continue
        if not is_data_node_copy(node_obj):
            continue
        block_id = resolve_copy_block_id(node_obj) or infer_copy_block_id_from_node_id(node_id)
        if not block_id:
            errors.append(f"副本 {node_id} 缺失 copy_block_id 且无法从命名推断")
            continue
        target_block = block_by_id.get(block_id)
        if target_block is None:
            errors.append(f"副本 {node_id} 指向不存在的块 {block_id}")
            continue
        block_data_nodes = set(getattr(target_block, "data_nodes", []) or [])
        if node_id not in block_data_nodes:
            errors.append(f"副本 {node_id} 未被归入其目标块 {block_id} 的 LayoutBlock.data_nodes")

    return errors


def _assert_original_data_not_multi_assigned_when_copy_enabled(
    augmented_model: Any,
    layout_blocks: List[Any],
) -> List[str]:
    """校验：启用跨块复制时，原始数据节点不应同时出现在多个块的 data_nodes 中。"""
    errors: List[str] = []
    nodes = getattr(augmented_model, "nodes", None)
    if not isinstance(nodes, dict):
        return ["augmented_model.nodes 不是 dict，无法审计"]

    membership: Dict[str, Set[str]] = {}
    for block in layout_blocks:
        order_index = int(getattr(block, "order_index", 0) or 0)
        block_id = f"block_{order_index}"
        data_nodes = list(getattr(block, "data_nodes", []) or [])
        for node_id in data_nodes:
            if not isinstance(node_id, str) or not node_id:
                continue
            node_obj = nodes.get(node_id)
            if node_obj is None:
                continue
            if is_data_node_copy(node_obj):
                continue
            membership.setdefault(node_id, set()).add(block_id)

    for node_id, blocks in membership.items():
        if len(blocks) > 1:
            canonical = resolve_canonical_original_id(node_id, model=augmented_model)
            errors.append(f"原始数据节点 {node_id} (canonical={canonical}) 同时归属多个块: {sorted(blocks)}")
    return errors


def _assert_copy_idempotency(
    augmented_model: Any,
    layout_blocks: List[Any],
    layout_context: LayoutContext,
) -> List[str]:
    """校验：在已经布局+复制后的增强模型上重复执行复制计划，不应新增副本/边。"""
    errors: List[str] = []

    before_node_count = len(getattr(augmented_model, "nodes", {}) or {})
    before_edge_count = len(getattr(augmented_model, "edges", {}) or {})
    before_copy_nodes = _snapshot_copy_nodes(augmented_model)

    manager = GlobalCopyManager(augmented_model, layout_blocks, layout_context)
    manager.analyze_dependencies()
    plan = manager.build_application_plan()
    manager.apply_application_plan(plan)

    after_node_count = len(getattr(augmented_model, "nodes", {}) or {})
    after_edge_count = len(getattr(augmented_model, "edges", {}) or {})
    after_copy_nodes = _snapshot_copy_nodes(augmented_model)

    if after_node_count != before_node_count:
        errors.append(f"幂等性失败：重复应用复制计划后 nodes 数量变化 {before_node_count} -> {after_node_count}")
    if after_edge_count != before_edge_count:
        errors.append(f"幂等性失败：重复应用复制计划后 edges 数量变化 {before_edge_count} -> {after_edge_count}")

    new_copy_nodes = sorted(after_copy_nodes - before_copy_nodes)
    if new_copy_nodes:
        errors.append(f"幂等性失败：重复应用复制计划后新增副本节点 {len(new_copy_nodes)} 个（示例: {new_copy_nodes[:5]}）")

    return errors


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python -X utf8 tools/audit_layout_copy_consistency.py <graph_py_path>")
        return 1

    code_path = _resolve_code_path(sys.argv[1])
    if not code_path.exists():
        print(f"文件不存在: {code_path}")
        return 1

    # GraphCodeParser 解析阶段会触发一次 quiet layout，需要 settings 中可推导 workspace_path
    settings.set_config_path(WORKSPACE)

    registry = get_node_registry(WORKSPACE, include_composite=True)
    node_library = registry.get_library()
    parser = GraphCodeParser(WORKSPACE, node_library=node_library, verbose=False)
    model, metadata = parser.parse_file(code_path)

    layout_result = LayoutService.compute_layout(
        model,
        node_library=node_library,
        include_augmented_model=True,
        clone_model=True,
        write_back_to_input_model=False,
        workspace_path=WORKSPACE,
    )

    augmented = layout_result.augmented_model
    if augmented is None:
        print("布局服务未返回增强模型（augmented_model is None）")
        return 1

    layout_blocks = _collect_layout_blocks_cache(augmented)
    if not layout_blocks:
        print("增强模型缺失 `_layout_blocks_cache`，无法审计跨块复制归属")
        return 1

    cached_context = getattr(augmented, "_layout_context_cache", None)
    if isinstance(cached_context, LayoutContext):
        layout_context = cached_context
    else:
        layout_context = LayoutContext(augmented)

    errors: List[str] = []

    errors.extend(_assert_copy_block_membership_consistent(augmented, layout_blocks))

    enable_copy = bool(getattr(settings, "DATA_NODE_CROSS_BLOCK_COPY", True))
    if enable_copy:
        errors.extend(_assert_original_data_not_multi_assigned_when_copy_enabled(augmented, layout_blocks))
        errors.extend(_assert_copy_idempotency(augmented, layout_blocks, layout_context))

    graph_id_value = getattr(augmented, "graph_id", metadata.get("graph_id", ""))
    print(f"[audit] graph_file={code_path}")
    print(f"[audit] graph_id={graph_id_value}")
    print(f"[audit] blocks={len(layout_blocks)} nodes={len(getattr(augmented, 'nodes', {}) or {})} edges={len(getattr(augmented, 'edges', {}) or {})}")
    print(f"[audit] copy_enabled={enable_copy}")

    if errors:
        print("[audit] FAILED")
        for item in errors:
            print(f"  - {item}")
        return 1

    print("[audit] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


