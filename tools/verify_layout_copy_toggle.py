"""
跨块复制开关的一致性校验：

目标：验证 UI 侧“克隆布局 + 差异合并”流程与引擎 LayoutService 的增强模型在
DATA_NODE_CROSS_BLOCK_COPY 打开/关闭两种模式下输出完全一致，避免副本节点与
边同步出现分叉。

用法（在项目根目录执行）:
  python -X utf8 -m tools.verify_layout_copy_toggle
  python -X utf8 -m tools.verify_layout_copy_toggle --tol 1.0 --max-files 0

判定规则：
  - 节点 ID 集合必须一致；
  - 边 ID 集合必须一致，且 src/dst/port 均相同；
  - 副本标记、原始节点 ID 与 copy_block_id 必须一致；
  - 坐标差的绝对值不超过 tol 视为等价；
  - basic_blocks 的节点列表必须一致（忽略顺序，逐块比较集合）。
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

# Windows 控制台 UTF-8
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")  # type: ignore[attr-defined]

if __package__:
    from ._bootstrap import ensure_workspace_root_on_sys_path
else:
    from _bootstrap import ensure_workspace_root_on_sys_path

WORKSPACE = ensure_workspace_root_on_sys_path()

from engine.configs.settings import settings  # noqa: E402
from engine.graph.models import BasicBlock, EdgeModel, GraphModel  # noqa: E402
from engine.layout import LayoutService  # noqa: E402
from engine.utils.cache.cache_paths import get_graph_cache_dir  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="验证跨块复制开关下 UI 差异合并与引擎增强模型的一致性",
    )
    parser.add_argument(
        "--tol",
        type=float,
        default=1.0,
        help="坐标容差（绝对值差 <= tol 视为一致）",
    )
    parser.add_argument(
        "--root",
        type=str,
        default=None,
        help="项目根目录，默认推导为脚本所在目录的上一层",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=0,
        help="仅校验前 N 个缓存文件，0 表示全量",
    )
    return parser.parse_args()


def resolve_cache_dir(root: Path) -> Path:
    cache_dir = get_graph_cache_dir(root)
    if not cache_dir.exists():
        raise FileNotFoundError(f"未找到 graph_cache 目录：{cache_dir}")
    return cache_dir


def load_cached_graph_data(cache_dir: Path, max_files: int = 0) -> List[tuple[str, dict]]:
    items: List[tuple[str, dict]] = []
    count_limit = max_files if max_files > 0 else None
    for file_path in sorted(cache_dir.glob("*.json")):
        data = json.loads(file_path.read_text(encoding="utf-8"))
        payload = data.get("result_data", {}) or {}
        graph_data = payload.get("data", {}) or {}
        graph_name = graph_data.get("graph_name", file_path.stem)
        items.append((graph_name, graph_data))
        if count_limit is not None and len(items) >= count_limit:
            break
    return items


def merge_augmented_into_model(target_model: GraphModel, augmented_model: GraphModel) -> None:
    model_node_ids_before: Set[str] = set(target_model.nodes.keys())
    model_edge_ids_before: Set[str] = set(target_model.edges.keys())
    augmented_node_ids: Set[str] = set(augmented_model.nodes.keys())
    augmented_edge_ids: Set[str] = set(augmented_model.edges.keys())

    nodes_to_add = augmented_node_ids - model_node_ids_before
    for node_id in nodes_to_add:
        target_model.nodes[node_id] = augmented_model.nodes[node_id]

    edges_to_add = augmented_edge_ids - model_edge_ids_before
    for edge_id in edges_to_add:
        target_model.edges[edge_id] = augmented_model.edges[edge_id]

    edges_to_remove = model_edge_ids_before - augmented_edge_ids
    for edge_id in edges_to_remove:
        target_model.edges.pop(edge_id, None)

    nodes_to_remove = model_node_ids_before - augmented_node_ids
    for node_id in list(nodes_to_remove):
        node_obj = target_model.nodes.get(node_id)
        if node_obj and getattr(node_obj, "is_data_node_copy", False):
            related_edge_ids = [
                edge_id
                for edge_id, edge_obj in target_model.edges.items()
                if edge_obj.src_node == node_id or edge_obj.dst_node == node_id
            ]
            for edge_id in related_edge_ids:
                target_model.edges.pop(edge_id, None)
            target_model.nodes.pop(node_id, None)

    positions_from_augmented: Dict[str, Tuple[float, float]] = {
        node_id: (float(node_obj.pos[0]), float(node_obj.pos[1])) if getattr(node_obj, "pos", None) else (0.0, 0.0)
        for node_id, node_obj in augmented_model.nodes.items()
    }
    for node_id, pos_tuple in positions_from_augmented.items():
        if node_id in target_model.nodes:
            target_model.nodes[node_id].pos = pos_tuple

    target_model.basic_blocks = list(augmented_model.basic_blocks or [])
    debug_map = getattr(augmented_model, "_layout_y_debug_info", None)
    if debug_map is not None:
        setattr(target_model, "_layout_y_debug_info", dict(debug_map))


def edge_signature(edge: EdgeModel) -> Tuple[str, str, str, str]:
    return (
        edge.src_node or "",
        edge.src_port or "",
        edge.dst_node or "",
        edge.dst_port or "",
    )


def block_signature(blocks: Iterable[BasicBlock]) -> List[Set[str]]:
    signatures: List[Set[str]] = []
    for block in blocks or []:
        node_ids = set(block.nodes or [])
        signatures.append(node_ids)
    return signatures


def compare_models(expected: GraphModel, actual: GraphModel, tol: float) -> List[str]:
    diffs: List[str] = []

    expected_nodes = set(expected.nodes.keys())
    actual_nodes = set(actual.nodes.keys())
    if expected_nodes != actual_nodes:
        missing_nodes = expected_nodes - actual_nodes
        extra_nodes = actual_nodes - expected_nodes
        if missing_nodes:
            diffs.append(f"缺失节点: {sorted(missing_nodes)[:10]}")
        if extra_nodes:
            diffs.append(f"多余节点: {sorted(extra_nodes)[:10]}")
        if len(missing_nodes) > 10 or len(extra_nodes) > 10:
            diffs.append("节点差异项超过 10 条，已截断")

    shared_nodes = expected_nodes & actual_nodes
    for node_id in sorted(shared_nodes):
        expected_node = expected.nodes[node_id]
        actual_node = actual.nodes[node_id]
        if bool(getattr(expected_node, "is_data_node_copy", False)) != bool(
            getattr(actual_node, "is_data_node_copy", False)
        ):
            diffs.append(f"副本标记不一致: {node_id}")
        expected_original = getattr(expected_node, "original_node_id", None)
        actual_original = getattr(actual_node, "original_node_id", None)
        if expected_original != actual_original:
            diffs.append(f"original_node_id 不一致: {node_id} expected={expected_original} actual={actual_original}")
        expected_copy_block = getattr(expected_node, "copy_block_id", None)
        actual_copy_block = getattr(actual_node, "copy_block_id", None)
        if expected_copy_block != actual_copy_block:
            diffs.append(
                f"copy_block_id 不一致: {node_id} expected={expected_copy_block} actual={actual_copy_block}"
            )
        expected_pos = getattr(expected_node, "pos", (0.0, 0.0)) or (0.0, 0.0)
        actual_pos = getattr(actual_node, "pos", (0.0, 0.0)) or (0.0, 0.0)
        dx = abs(float(actual_pos[0]) - float(expected_pos[0]))
        dy = abs(float(actual_pos[1]) - float(expected_pos[1]))
        if dx > tol or dy > tol:
            diffs.append(
                f"坐标差异: {node_id} dx={dx:.2f} dy={dy:.2f} expected=({expected_pos[0]:.1f},{expected_pos[1]:.1f}) "
                f"actual=({actual_pos[0]:.1f},{actual_pos[1]:.1f})"
            )

    expected_edges = set(expected.edges.keys())
    actual_edges = set(actual.edges.keys())
    if expected_edges != actual_edges:
        missing_edges = expected_edges - actual_edges
        extra_edges = actual_edges - expected_edges
        if missing_edges:
            diffs.append(f"缺失边: {sorted(missing_edges)[:10]}")
        if extra_edges:
            diffs.append(f"多余边: {sorted(extra_edges)[:10]}")
        if len(missing_edges) > 10 or len(extra_edges) > 10:
            diffs.append("边差异项超过 10 条，已截断")

    shared_edges = expected_edges & actual_edges
    for edge_id in sorted(shared_edges):
        expected_edge = expected.edges[edge_id]
        actual_edge = actual.edges[edge_id]
        if edge_signature(expected_edge) != edge_signature(actual_edge):
            diffs.append(
                f"边端口不一致: {edge_id} "
                f"expected={edge_signature(expected_edge)} actual={edge_signature(actual_edge)}"
            )

    expected_blocks = block_signature(expected.basic_blocks)
    actual_blocks = block_signature(actual.basic_blocks)
    if len(expected_blocks) != len(actual_blocks):
        diffs.append(f"basic_blocks 数量不一致: expected={len(expected_blocks)} actual={len(actual_blocks)}")
    else:
        for index, (expected_set, actual_set) in enumerate(zip(expected_blocks, actual_blocks), start=1):
            if expected_set != actual_set:
                diffs.append(
                    f"basic_blocks 第 {index} 个节点集合不一致: "
                    f"expected={sorted(expected_set)} actual={sorted(actual_set)}"
                )

    return diffs


def verify_one_graph(graph_name: str, graph_data: dict, enable_copy: bool, tol: float, *, workspace_path: Path) -> List[str]:
    settings.DATA_NODE_CROSS_BLOCK_COPY = bool(enable_copy)
    model_for_layout = GraphModel.deserialize(graph_data)
    layout_result = LayoutService.compute_layout(
        model_for_layout,
        include_augmented_model=True,
        clone_model=True,
        write_back_to_input_model=False,
        workspace_path=workspace_path,
    )
    augmented_model = layout_result.augmented_model
    if augmented_model is None:
        return [f"[ERROR] {graph_name} 未返回增强模型，无法对比"]
    ui_model = GraphModel.deserialize(graph_data)
    merge_augmented_into_model(ui_model, augmented_model)
    return compare_models(augmented_model, ui_model, tol)


def run_verification(tol: float, max_files: int, root: Path) -> int:
    cache_dir = resolve_cache_dir(root)
    entries = load_cached_graph_data(cache_dir, max_files=max_files)
    if not entries:
        print("[ERROR] 未找到任何缓存的图数据。请先运行主程序或相关工具生成 graph_cache。")
        return 2

    original_flag = bool(getattr(settings, "DATA_NODE_CROSS_BLOCK_COPY", True))
    total_graphs = len(entries)
    scenario_count = total_graphs * 2
    failures = 0

    for enable_copy in (True, False):
        print("=" * 72)
        print(f"[MODE] DATA_NODE_CROSS_BLOCK_COPY = {enable_copy}")
        for graph_name, graph_data in entries:
            diffs = verify_one_graph(graph_name, graph_data, enable_copy, tol, workspace_path=root)
            if diffs:
                failures += 1
                print(f"[DIFF] {graph_name} 差异 {len(diffs)} 项")
                for detail in diffs[:10]:
                    print(f"  - {detail}")
                if len(diffs) > 10:
                    print(f"  ... 其余 {len(diffs) - 10} 项省略")
            else:
                print(f"[OK] {graph_name}")

    settings.DATA_NODE_CROSS_BLOCK_COPY = original_flag

    print("=" * 72)
    print(f"总用例: {scenario_count}  差异: {failures}  通过: {scenario_count - failures}")
    return 0 if failures == 0 else 1


def main() -> int:
    args = parse_args()
    root = Path(args.root) if args.root else WORKSPACE
    return run_verification(tol=args.tol, max_files=args.max_files, root=root)


if __name__ == "__main__":
    sys.exit(main())

