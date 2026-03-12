from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from engine.graph.graph_code_parser import GraphCodeParser
from engine.layout.internal.constants import NODE_WIDTH_DEFAULT
from engine.layout.utils.graph_query_utils import estimate_node_height_ui_exact_with_context, is_flow_edge
from tests._helpers.project_paths import get_repo_root


UI_BLOCK_RECT_MARGIN: float = 25.0


@dataclass(frozen=True)
class BlockUiRect:
    x: float
    y: float
    w: float
    h: float

    @property
    def center_y(self) -> float:
        return float(self.y) + float(self.h) * 0.5


def _build_basic_block_index_by_node_id(*, model: object) -> dict[str, int]:
    blocks = list(getattr(model, "basic_blocks", []) or [])
    node_to_index: dict[str, int] = {}
    for block in blocks:
        order_index = int(getattr(block, "order_index", 0) or 0)
        for node_id in list(getattr(block, "nodes", []) or []):
            if isinstance(node_id, str) and node_id:
                node_to_index[node_id] = order_index
    return node_to_index


def _compute_ui_like_block_rect(*, model: object, node_ids: list[str]) -> BlockUiRect | None:
    nodes = getattr(model, "nodes", None)
    if not isinstance(nodes, dict) or not node_ids:
        return None
    layout_context = getattr(model, "_layout_context_cache", None)
    if layout_context is None:
        raise AssertionError(
            "模型缺少 _layout_context_cache；请确保该 graph_file 解析后已执行布局并写回缓存。"
        )

    min_x: float | None = None
    min_y: float | None = None
    max_x: float | None = None
    max_y: float | None = None

    for node_id in node_ids:
        node = nodes.get(node_id)
        pos = getattr(node, "pos", None) if node is not None else None
        if not isinstance(pos, (list, tuple)) or len(pos) < 2:
            continue
        x = float(pos[0])
        y = float(pos[1])
        node_w = float(NODE_WIDTH_DEFAULT)
        node_h = float(estimate_node_height_ui_exact_with_context(layout_context, node_id))
        x2 = x + float(node_w)
        y2 = y + float(node_h)
        if min_x is None:
            min_x, min_y, max_x, max_y = x, y, x2, y2
        else:
            min_x = min(float(min_x), x)
            min_y = min(float(min_y), y)
            max_x = max(float(max_x), x2)
            max_y = max(float(max_y), y2)

    if min_x is None or min_y is None or max_x is None or max_y is None:
        return None

    x = float(min_x) - float(UI_BLOCK_RECT_MARGIN)
    y = float(min_y) - float(UI_BLOCK_RECT_MARGIN)
    w = float(max_x) - float(min_x) + float(UI_BLOCK_RECT_MARGIN) * 2.0
    h = float(max_y) - float(min_y) + float(UI_BLOCK_RECT_MARGIN) * 2.0
    return BlockUiRect(x=x, y=y, w=w, h=h)


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


def main() -> int:
    repo_root = get_repo_root()
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph-file", type=str, default=str(_default_graph_file(repo_root=repo_root)))
    parser.add_argument("--parent", type=int, required=True, help="要检查的父块编号（UI 红色块号 / BasicBlock.order_index）")
    args = parser.parse_args()

    graph_file = Path(str(args.graph_file))
    parent_index = int(args.parent)

    code_parser = GraphCodeParser(repo_root)
    model, _meta = code_parser.parse_file(graph_file)

    # 1) ordered_children（布局缓存快照）
    snapshot = getattr(model, "_layout_block_relationships", None)
    ordered_children = snapshot.get("ordered_children") if isinstance(snapshot, dict) else None
    if not isinstance(ordered_children, dict):
        raise AssertionError("模型未包含 _layout_block_relationships['ordered_children']（解析+布局未生效）")
    ordered_children_by_index: dict[int, list[int]] = {}
    for parent_blk, children_blks in ordered_children.items():
        p = int(getattr(parent_blk, "order_index", 0) or 0)
        if p <= 0:
            continue
        ordered_children_by_index[p] = [
            int(getattr(c, "order_index", 0) or 0) for c in list(children_blks or [])
        ]

    # 2) UI 的 basic_blocks + 任意 flow 边跨块连边（更贴近 UI “块连接”观感）
    node_to_block_index = _build_basic_block_index_by_node_id(model=model)
    ui_children_by_index: dict[int, set[int]] = {}
    edges = getattr(model, "edges", None)
    if isinstance(edges, dict):
        for edge in edges.values():
            if not is_flow_edge(model, edge):
                continue
            src = getattr(edge, "src_node", None)
            dst = getattr(edge, "dst_node", None)
            if not isinstance(src, str) or not isinstance(dst, str):
                continue
            src_idx = node_to_block_index.get(src)
            dst_idx = node_to_block_index.get(dst)
            if not isinstance(src_idx, int) or not isinstance(dst_idx, int):
                continue
            if src_idx == dst_idx:
                continue
            ui_children_by_index.setdefault(int(src_idx), set()).add(int(dst_idx))

    # 3) 打印 parent 的关键对比与 center_y
    basic_blocks = list(getattr(model, "basic_blocks", []) or [])
    parent_block = next((b for b in basic_blocks if int(getattr(b, "order_index", 0) or 0) == parent_index), None)
    if parent_block is None:
        raise AssertionError(f"未找到 BasicBlock.order_index == {parent_index}")
    parent_nodes = [str(n) for n in list(getattr(parent_block, "nodes", []) or []) if isinstance(n, str)]
    parent_rect = _compute_ui_like_block_rect(model=model, node_ids=parent_nodes)
    if parent_rect is None:
        raise AssertionError(f"无法计算 parent={parent_index} 的 UI-like block rect（节点坐标缺失）")

    ui_children = sorted(list(ui_children_by_index.get(parent_index, set())))
    snap_children = ordered_children_by_index.get(parent_index, [])

    def _child_center(child_index: int) -> float | None:
        child_blk = next((b for b in basic_blocks if int(getattr(b, "order_index", 0) or 0) == child_index), None)
        if child_blk is None:
            return None
        child_nodes = [str(n) for n in list(getattr(child_blk, "nodes", []) or []) if isinstance(n, str)]
        rect = _compute_ui_like_block_rect(model=model, node_ids=child_nodes)
        return rect.center_y if rect is not None else None

    print(f"[graph_file] {graph_file}")
    print(f"[parent] {parent_index}")
    print(f"[parent.center_y(ui_like)] {parent_rect.center_y}")
    print(f"[children.by_any_flow_edge] {ui_children}")
    print(f"[children.by_layout_snapshot_ordered_children] {snap_children}")
    if ui_children:
        centers = [(c, _child_center(c)) for c in ui_children]
        print(f"[children.center_y(ui_like)] {centers}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

