from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from engine.graph.graph_code_parser import GraphCodeParser
from engine.layout.utils.graph_query_utils import estimate_node_height_ui_exact_with_context
from tests._helpers.project_paths import get_repo_root


TOP_K: int = 10


@dataclass(frozen=True)
class NodeYInfo:
    node_id: str
    y: float
    h: float


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
    parser.add_argument("--top-k", type=int, default=TOP_K)
    args = parser.parse_args()

    graph_file = Path(str(args.graph_file))
    top_k = int(args.top_k)
    if top_k <= 0:
        top_k = TOP_K

    code_parser = GraphCodeParser(repo_root)
    model, _meta = code_parser.parse_file(graph_file)

    layout_context = getattr(model, "_layout_context_cache", None)
    if layout_context is None:
        raise AssertionError("模型缺少 _layout_context_cache（无法按UI口径估算节点高度）")

    nodes = getattr(model, "nodes", None)
    if not isinstance(nodes, dict):
        raise AssertionError("model.nodes 缺失")

    infos: list[NodeYInfo] = []
    for node_id, node_obj in nodes.items():
        pos = getattr(node_obj, "pos", None)
        if not isinstance(pos, (list, tuple)) or len(pos) < 2:
            continue
        y = float(pos[1])
        h = float(estimate_node_height_ui_exact_with_context(layout_context, str(node_id)))
        infos.append(NodeYInfo(node_id=str(node_id), y=y, h=h))

    if not infos:
        raise AssertionError("未收集到任何节点坐标")

    max_y = max(info.y for info in infos)
    min_y = min(info.y for info in infos)
    max_y2 = max((info.y + info.h) for info in infos)
    min_y2 = min((info.y + info.h) for info in infos)

    print(f"[graph_file] {graph_file}")
    print(f"[nodes] {len(infos)}")
    print(f"[y.min] {min_y}")
    print(f"[y.max] {max_y}")
    print(f"[y2.min] {min_y2}")
    print(f"[y2.max] {max_y2}")

    by_y_desc = sorted(infos, key=lambda i: i.y, reverse=True)[:top_k]
    print(f"[top_nodes_by_y] (top_k={top_k})")
    for item in by_y_desc:
        print(f"- node_id={item.node_id} y={item.y} h={item.h} y2={item.y + item.h}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

