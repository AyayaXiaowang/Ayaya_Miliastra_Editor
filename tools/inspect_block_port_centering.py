from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from engine.graph.graph_code_parser import GraphCodeParser
from engine.layout.internal.constants import UI_HEADER_EXTRA, UI_NODE_PADDING, UI_ROW_HEIGHT
from engine.layout.utils.graph_query_utils import build_input_port_layout_plan, is_flow_edge
from tests._helpers.project_paths import get_repo_root


HALF_ROW_HEIGHT_PX: int = int(UI_ROW_HEIGHT) // 2
NODE_HEADER_HEIGHT_PX: int = int(UI_ROW_HEIGHT) + int(UI_HEADER_EXTRA)
PORT_START_Y_PX: int = int(NODE_HEADER_HEIGHT_PX) + int(UI_NODE_PADDING)


@dataclass(frozen=True)
class PortAnchor:
    src_node_id: str
    src_port: str
    src_port_y: float
    dst_node_id: str
    dst_port: str
    dst_port_y: float


def _default_graph_file(*, repo_root: Path) -> Path:
    return (
        repo_root
        / "assets"
        / "资源库"
        / "项目存档"
        / "测试项目"
        / "节点图"
        / "server"
        / "实体节点图"
        / "回归"
        / "布局回归_列表迭代与分支_压力图"
        / "布局回归_列表迭代与分支_压力图.py"
    )


def _build_basic_block_index_by_node_id(*, model: object) -> dict[str, int]:
    blocks = list(getattr(model, "basic_blocks", []) or [])
    node_to_index: dict[str, int] = {}
    for block in blocks:
        order_index = int(getattr(block, "order_index", 0) or 0)
        for node_id in list(getattr(block, "nodes", []) or []):
            if isinstance(node_id, str) and node_id:
                node_to_index[node_id] = order_index
    return node_to_index


def _connected_input_ports_for_node(*, model: object, node_id: str) -> set[str]:
    edges = getattr(model, "edges", None)
    if not isinstance(edges, dict):
        return set()
    ports: set[str] = set()
    for edge in edges.values():
        if str(getattr(edge, "dst_node", "") or "") != node_id:
            continue
        dst_port = str(getattr(edge, "dst_port", "") or "")
        if dst_port:
            ports.add(dst_port)
    return ports


def _resolve_output_port_index(*, node_obj: object, port_name: str) -> int | None:
    outputs = list(getattr(node_obj, "outputs", []) or [])
    for idx, p in enumerate(outputs):
        name = str(getattr(p, "name", "") or "")
        if name == port_name:
            return int(idx)
    return None


def _port_center_y_output(*, node_pos_y: float, output_index: int) -> float:
    # UI: output_start_y = header_height + NODE_PADDING
    #     port_y = output_start_y + output_index*ROW_HEIGHT + ROW_HEIGHT//2
    local_y = float(PORT_START_Y_PX + int(output_index) * int(UI_ROW_HEIGHT) + int(HALF_ROW_HEIGHT_PX))
    return float(node_pos_y) + local_y


def _port_center_y_input(*, model: object, layout_context: object, node_obj: object, node_pos_y: float, port_name: str) -> float:
    registry_context = getattr(layout_context, "registry_context", None)
    if registry_context is None:
        raise AssertionError("layout_context 缺少 registry_context，无法按 UI 口径计算输入端口行号")
    connected = _connected_input_ports_for_node(model=model, node_id=str(getattr(node_obj, "id", "") or ""))
    plan = build_input_port_layout_plan(node_obj, connected, registry_context=registry_context)
    row_index = int(plan.row_index_by_port.get(port_name, 0))
    local_y = float(PORT_START_Y_PX + row_index * int(UI_ROW_HEIGHT) + int(HALF_ROW_HEIGHT_PX))
    return float(node_pos_y) + local_y


def main() -> int:
    repo_root = get_repo_root()
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph-file", type=str, default=str(_default_graph_file(repo_root=repo_root)))
    parser.add_argument("--parent", type=int, required=True, help="父块编号（UI 红色块号 / BasicBlock.order_index）")
    args = parser.parse_args()

    graph_file = Path(str(args.graph_file))
    parent_index = int(args.parent)

    code_parser = GraphCodeParser(repo_root)
    model, _meta = code_parser.parse_file(graph_file)

    layout_context = getattr(model, "_layout_context_cache", None)
    if layout_context is None:
        raise AssertionError("模型缺少 _layout_context_cache（无法按 UI 口径计算端口坐标）")

    node_to_block_index = _build_basic_block_index_by_node_id(model=model)
    nodes = getattr(model, "nodes", None)
    edges = getattr(model, "edges", None)
    if not isinstance(nodes, dict) or not isinstance(edges, dict):
        raise AssertionError("model.nodes/model.edges 缺失")

    # 汇总：parent -> {child -> 一条代表性 anchor（按输出端口顺序取第一条）}
    anchors_by_child: dict[int, PortAnchor] = {}
    for edge in edges.values():
        if not is_flow_edge(model, edge):
            continue
        src_node_id = str(getattr(edge, "src_node", "") or "")
        dst_node_id = str(getattr(edge, "dst_node", "") or "")
        if not src_node_id or not dst_node_id:
            continue
        src_idx = node_to_block_index.get(src_node_id)
        dst_idx = node_to_block_index.get(dst_node_id)
        if src_idx != parent_index:
            continue
        if not isinstance(dst_idx, int) or dst_idx == parent_index:
            continue

        src_port = str(getattr(edge, "src_port", "") or "")
        dst_port = str(getattr(edge, "dst_port", "") or "")
        if not src_port or not dst_port:
            continue

        src_node = nodes.get(src_node_id)
        dst_node = nodes.get(dst_node_id)
        if src_node is None or dst_node is None:
            continue
        src_pos = getattr(src_node, "pos", None)
        dst_pos = getattr(dst_node, "pos", None)
        if not (isinstance(src_pos, (list, tuple)) and len(src_pos) >= 2):
            continue
        if not (isinstance(dst_pos, (list, tuple)) and len(dst_pos) >= 2):
            continue

        out_index = _resolve_output_port_index(node_obj=src_node, port_name=src_port)
        if out_index is None:
            continue

        src_port_y = _port_center_y_output(node_pos_y=float(src_pos[1]), output_index=out_index)
        dst_port_y = _port_center_y_input(
            model=model,
            layout_context=layout_context,
            node_obj=dst_node,
            node_pos_y=float(dst_pos[1]),
            port_name=dst_port,
        )

        existing = anchors_by_child.get(int(dst_idx))
        if existing is None:
            anchors_by_child[int(dst_idx)] = PortAnchor(
                src_node_id=src_node_id,
                src_port=src_port,
                src_port_y=float(src_port_y),
                dst_node_id=dst_node_id,
                dst_port=dst_port,
                dst_port_y=float(dst_port_y),
            )
            continue

        # 已有 anchor：按“输出端口顺序更靠上”的优先（更贴近 UI 端口从上到下的阅读顺序）
        if float(src_port_y) < float(existing.src_port_y):
            anchors_by_child[int(dst_idx)] = PortAnchor(
                src_node_id=src_node_id,
                src_port=src_port,
                src_port_y=float(src_port_y),
                dst_node_id=dst_node_id,
                dst_port=dst_port,
                dst_port_y=float(dst_port_y),
            )

    children = sorted(list(anchors_by_child.keys()))
    print(f"[graph_file] {graph_file}")
    print(f"[parent_block] {parent_index}")
    print(f"[children_blocks] {children}")
    if len(children) < 2:
        print("[note] 子块不足2个，无法判断居中")
        return 0

    anchors = [anchors_by_child[c] for c in children]
    parent_anchor_y_mean = sum(a.src_port_y for a in anchors) / float(len(anchors))
    child_anchor_ys = [a.dst_port_y for a in anchors]
    lo = min(child_anchor_ys)
    hi = max(child_anchor_ys)
    print(f"[parent_anchor_y_mean] {parent_anchor_y_mean}")
    print(f"[children_anchor_y_range] [{lo}, {hi}]")
    print("[anchors]")
    for c in children:
        a = anchors_by_child[c]
        print(
            f"- child_block={c} "
            f"src=({a.src_node_id}.{a.src_port} y={a.src_port_y}) "
            f"dst=({a.dst_node_id}.{a.dst_port} y={a.dst_port_y})"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

