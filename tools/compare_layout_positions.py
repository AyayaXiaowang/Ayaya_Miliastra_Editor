"""
比较 graph_cache 中缓存坐标与当前 LayoutService 结果。

默认忽略跨块复制（is_data_node_copy=True）的节点，仅关注原始节点。
附带统计：复制节点数量、哪些节点缺少调试信息等，便于排查
“积分榜_排序控制终端”等大图的 Y 排序问题。

用法（项目根目录）：
    python -X utf8 -m tools.compare_layout_positions server_scoreboard_controller_01 [tol]
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Dict, Tuple, List, Set
from collections import defaultdict, deque

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")  # type: ignore[attr-defined]

if __package__:
    from ._bootstrap import ensure_workspace_root_on_sys_path
else:
    from _bootstrap import ensure_workspace_root_on_sys_path

WORKSPACE = ensure_workspace_root_on_sys_path()

from engine.graph.models import GraphModel  # noqa: E402
from engine.layout import LayoutService  # noqa: E402
from engine.configs.settings import settings  # noqa: E402
from engine.utils.graph.graph_utils import is_flow_port_name  # noqa: E402


def _load_graph(target_name: str) -> Tuple[GraphModel, Path]:
    cache_dir = WORKSPACE / "app" / "runtime" / "cache" / "graph_cache"
    if not cache_dir.exists():
        print("[ERROR] 未找到 app/runtime/cache/graph_cache")
        sys.exit(2)
    normalized = target_name.strip().lower()
    for entry in sorted(cache_dir.glob("*.json")):
        data = json.loads(entry.read_text(encoding="utf-8"))
        payload = data.get("result_data", {}) or {}
        graph_data = payload.get("data", {}) or {}
        graph_id = str(graph_data.get("graph_id") or "").lower()
        cache_key = entry.stem.lower()
        if normalized in (graph_id, cache_key):
            return GraphModel.deserialize(graph_data), entry
    print(f"[ERROR] 未在 graph_cache 中找到图：{target_name}")
    sys.exit(2)


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python -X utf8 tools/compare_layout_positions.py <graph_id_or_cache_name> [tol] [--reset]")
        return 1
    target = sys.argv[1]
    tol = 1.0
    reset_positions = False
    for arg in sys.argv[2:]:
        if arg == "--reset":
            reset_positions = True
        else:
            tol = float(arg)

    model, cache_file = _load_graph(target)
    settings.SHOW_LAYOUT_Y_DEBUG = True
    if reset_positions:
        for node in model.nodes.values():
            node.pos = (100.0, 100.0)
    baseline_positions: Dict[str, Tuple[float, float]] = {
        nid: (float(node.pos[0]), float(node.pos[1])) for nid, node in model.nodes.items()
    }
    print(f"[INFO] 图：{model.graph_name} ({model.graph_id})")
    print(f"[INFO] 缓存文件：{cache_file}")
    print(f"[INFO] 节点总数：{len(model.nodes)}")

    # 运行布局（包含增强模型以便识别副本节点）
    result = LayoutService.compute_layout(model, include_augmented_model=True, workspace_path=WORKSPACE)
    augmented = getattr(result, "augmented_model", None)
    if augmented is None:
        print("[ERROR] 布局结果缺少 augmented_model（无法判断副本节点）")
        return 2

    copy_flags: Dict[str, bool] = {}
    for node_id, node in augmented.nodes.items():
        copy_flags[node_id] = bool(getattr(node, "is_data_node_copy", False))

    filtered_positions: Dict[str, Tuple[float, float]] = {}
    for node_id, pos in result.positions.items():
        if copy_flags.get(node_id):
            continue
        filtered_positions[node_id] = (float(pos[0]), float(pos[1]))

    missing_nodes = sorted(set(baseline_positions.keys()) - set(filtered_positions.keys()))
    extra_nodes = sorted(set(filtered_positions.keys()) - set(baseline_positions.keys()))
    if missing_nodes:
        print(f"[WARN] 有 {len(missing_nodes)} 个原始节点在新布局中缺失（忽略副本后）。示例：{missing_nodes[:5]}")
    if extra_nodes:
        print(f"[WARN] 有 {len(extra_nodes)} 个新节点（非副本）出现在布局结果中。示例：{extra_nodes[:5]}")

    diffs = []
    diff_map: Dict[str, Tuple[float, float]] = {}
    for node_id, (bx, by) in baseline_positions.items():
        new_pos = filtered_positions.get(node_id)
        if not new_pos:
            continue
        nx, ny = new_pos
        dx = abs(nx - bx)
        dy = abs(ny - by)
        if dx > tol or dy > tol:
            diffs.append((node_id, dx, dy, (bx, by), (nx, ny)))
            diff_map[node_id] = (dx, dy)
    diffs.sort(key=lambda item: max(item[1], item[2]), reverse=True)

    print(f"[INFO] 副本节点数量：{sum(1 for flag in copy_flags.values() if flag)}")
    if diffs:
        print(f"[DIFF] 共有 {len(diffs)} 个节点超出容差 {tol:.2f} 像素（仅统计原始节点）。前10条：")
        for node_id, dx, dy, (bx, by), (nx, ny) in diffs[:10]:
            print(f"  - {node_id}: dx={dx:.2f}, dy={dy:.2f}  baseline=({bx:.1f},{by:.1f}) now=({nx:.1f},{ny:.1f})")
    else:
        print("[OK] 所有原始节点的位置均在容差范围内。")

    # 事件级统计：哪些事件流的节点被重新定位
    event_assignments = _build_event_assignments(model)
    event_total_counts: Dict[str, int] = defaultdict(int)
    event_changed_counts: Dict[str, int] = defaultdict(int)
    for node_id in baseline_positions.keys():
        event_id = event_assignments.get(node_id, "<无事件>")
        event_total_counts[event_id] += 1
        if node_id in diff_map:
            event_changed_counts[event_id] += 1
    if event_total_counts:
        print("[INFO] 按事件统计重新定位的节点数：")
        for event_id, total in event_total_counts.items():
            changed = event_changed_counts.get(event_id, 0)
            title = _resolve_event_title(model, event_id)
            print(f"  - {title or event_id}: {changed}/{total} 节点发生位移")

    debug_map = result.y_debug_info or {}
    copy_without_debug = [
        node_id for node_id, is_copy in copy_flags.items() if is_copy and node_id not in debug_map
    ]
    if copy_without_debug:
        print(f"[WARN] 有 {len(copy_without_debug)} 个副本节点缺少布局Y调试信息。示例：{copy_without_debug[:5]}")
    else:
        print("[OK] 所有副本节点均有布局Y调试信息。")

    return 0


def _build_event_assignments(model: GraphModel) -> Dict[str, str]:
    """基于流程与数据连线，为节点标记所属事件ID。"""
    event_ids: List[str] = []
    if isinstance(getattr(model, "event_flow_order", None), list):
        event_ids = [event_id for event_id in model.event_flow_order if event_id in model.nodes]
    if not event_ids:
        event_ids = [node.id for node in model.nodes.values() if node.category == "事件节点"]

    flow_adjacency: Dict[str, List[str]] = defaultdict(list)
    data_neighbors = _build_data_neighbors(model)
    for edge in model.edges.values():
        src_node = model.nodes.get(edge.src_node)
        if not src_node:
            continue
        port = src_node.get_output_port(edge.src_port)
        if port and is_flow_port_name(port.name):
            flow_adjacency[edge.src_node].append(edge.dst_node)

    assignments: Dict[str, str] = {}
    for event_id in event_ids:
        if event_id not in model.nodes:
            continue
        queue: deque[str] = deque([event_id])
        while queue:
            current = queue.popleft()
            if current in assignments:
                continue
            assignments[current] = event_id
            for child in flow_adjacency.get(current, []):
                if child not in assignments:
                    queue.append(child)

    _propagate_event_to_data_nodes(assignments, data_neighbors)
    return assignments


def _build_data_neighbors(model: GraphModel) -> Dict[str, Set[str]]:
    """构建数据边的无向邻接表，用于事件归属扩散。"""
    neighbors: Dict[str, Set[str]] = defaultdict(set)
    for edge in model.edges.values():
        dst_node = model.nodes.get(edge.dst_node)
        if not dst_node:
            continue
        dst_port = dst_node.get_input_port(edge.dst_port)
        if not dst_port or is_flow_port_name(dst_port.name):
            continue
        neighbors[edge.src_node].add(edge.dst_node)
        neighbors[edge.dst_node].add(edge.src_node)
    return neighbors


def _propagate_event_to_data_nodes(assignments: Dict[str, str], data_neighbors: Dict[str, Set[str]]) -> None:
    """将事件归属从流程节点扩散到纯数据节点（仅在唯一事件可判定时写入）。"""
    if not data_neighbors or not assignments:
        return
    queue: deque[str] = deque(assignments.keys())
    processed: Set[str] = set()
    while queue:
        current = queue.popleft()
        if current in processed:
            continue
        processed.add(current)
        for neighbor in data_neighbors.get(current, ()):
            if neighbor in assignments:
                continue
            neighbor_events = {
                assignments.get(adjacent)
                for adjacent in data_neighbors.get(neighbor, ())
                if assignments.get(adjacent)
            }
            if len(neighbor_events) == 1:
                event_id = neighbor_events.pop()
                assignments[neighbor] = event_id
                queue.append(neighbor)


def _resolve_event_title(model: GraphModel, event_id: str) -> str:
    titles = getattr(model, "event_flow_titles", None)
    if isinstance(titles, list):
        for idx, evt in enumerate(getattr(model, "event_flow_order", []) or []):
            if evt == event_id and idx < len(titles):
                return str(titles[idx])
    node = model.nodes.get(event_id)
    if node:
        return node.title
    return event_id


if __name__ == "__main__":
    sys.exit(main())

