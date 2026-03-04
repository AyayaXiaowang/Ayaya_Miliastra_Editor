from __future__ import annotations

"""
tools.diff_graph_ir

离线诊断工具：对比两份 `parse_gil_payload_to_graph_ir --no-markdown` 产生的 Graph IR(JSON)：
- edges：基于 OutFlow/OutParam pins 的 connects 还原边集合，输出 missing/extra（可用于定位“缺边”问题）
- pins：聚焦 `concrete_index_of_concrete_int` 的差异（常见于泛型/反射端口的 concrete 选择不一致）

运行：
  python -X utf8 -m tools.diff_graph_ir --a <graph_ir_a.json> --b <graph_ir_b.json> --label-a A --label-b B
"""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


@dataclass(frozen=True, slots=True)
class Edge:
    src_node: int
    src_kind: int
    src_index: int
    dst_node: int
    dst_kind: int
    dst_index: int


def _load_json(path: Path) -> Any:
    p = Path(path).resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))
    return json.loads(p.read_text(encoding="utf-8"))


def _iter_nodes(graph_ir: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    nodes = graph_ir.get("nodes")
    if not isinstance(nodes, list):
        raise TypeError("graph_ir.nodes must be list")
    for n in nodes:
        if isinstance(n, dict):
            yield n


def _build_node_map(graph_ir: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for n in _iter_nodes(graph_ir):
        idx = n.get("node_index_int")
        if isinstance(idx, int):
            out[int(idx)] = n
    return out


def _iter_edges_from_out_pins(graph_ir: Dict[str, Any]) -> Set[Edge]:
    """
    从 pins.connects 反推边集合（以 **输入 pin 的 connects** 为准）。

    约定（Graph IR schema_version=2）：
    - 绝大多数 `.gil` 中，连接信息主要挂在 InFlow/InParam 上（即：输入 pin 记录远端输出 pin）。
    - kind_int=2 表示 InFlow（flow in）
    - kind_int=3 表示 InParam（data in）
    - connect.kind_int/index_int 表示远端 pin（OutFlow/OutParam）的 kind/index
    """
    edges: set[Edge] = set()
    for n in _iter_nodes(graph_ir):
        dst_node = n.get("node_index_int")
        if not isinstance(dst_node, int):
            continue
        pins = n.get("pins")
        if not isinstance(pins, list):
            continue
        for p in pins:
            if not isinstance(p, dict):
                continue
            pin_kind = p.get("kind_int")
            if not isinstance(pin_kind, int):
                continue
            if int(pin_kind) not in (2, 3):
                continue
            pin_index = p.get("index_int")
            if not isinstance(pin_index, int):
                continue
            connects = p.get("connects")
            if not isinstance(connects, list):
                continue
            for c in connects:
                if not isinstance(c, dict):
                    continue
                src_node = c.get("remote_node_index_int")
                if not isinstance(src_node, int):
                    continue
                connect = c.get("connect")
                if not isinstance(connect, dict):
                    continue
                connect_kind = connect.get("kind_int")
                connect_index = connect.get("index_int")
                if not isinstance(connect_kind, int) or not isinstance(connect_index, int):
                    continue
                edges.add(
                    Edge(
                        src_node=int(src_node),
                        src_kind=int(connect_kind),
                        src_index=int(connect_index),
                        dst_node=int(dst_node),
                        dst_kind=int(pin_kind),
                        dst_index=int(pin_index),
                    )
                )
    return edges


def _pin_key(pin: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    k = pin.get("kind_int")
    i = pin.get("index_int")
    if isinstance(k, int) and isinstance(i, int):
        return (int(k), int(i))
    return None


def _build_pin_map(node: Dict[str, Any]) -> Dict[Tuple[int, int], Dict[str, Any]]:
    pins = node.get("pins")
    if not isinstance(pins, list):
        return {}
    out: Dict[Tuple[int, int], Dict[str, Any]] = {}
    for p in pins:
        if not isinstance(p, dict):
            continue
        key = _pin_key(p)
        if key is None:
            continue
        out[key] = p
    return out


def _print_edge(e: Edge) -> str:
    kind_map = {4: "out", 5: "flow", 3: "in", 2: "in_flow", 1: "out_flow"}
    return (
        f"src({e.src_node}).{kind_map.get(e.src_kind, str(e.src_kind))}[{e.src_index}]"
        f" -> dst({e.dst_node}).{kind_map.get(e.dst_kind, str(e.dst_kind))}[{e.dst_index}]"
    )


def _diff_graph_ir(a: Dict[str, Any], b: Dict[str, Any], *, label_a: str, label_b: str) -> None:
    edges_a = _iter_edges_from_out_pins(a)
    edges_b = _iter_edges_from_out_pins(b)
    missing = sorted(
        list(edges_b - edges_a),
        key=lambda e: (e.src_node, e.src_kind, e.src_index, e.dst_node, e.dst_kind, e.dst_index),
    )
    extra = sorted(
        list(edges_a - edges_b),
        key=lambda e: (e.src_node, e.src_kind, e.src_index, e.dst_node, e.dst_kind, e.dst_index),
    )

    print("=" * 100)
    print(
        f"edges: {label_a}={len(edges_a)} {label_b}={len(edges_b)} "
        f"missing_in_{label_a}={len(missing)} extra_in_{label_a}={len(extra)}"
    )
    if missing:
        print(f"- missing_in_{label_a} (head 20):")
        for e in missing[:20]:
            print(f"  - {_print_edge(e)}")
    if extra:
        print(f"- extra_in_{label_a} (head 20):")
        for e in extra[:20]:
            print(f"  - {_print_edge(e)}")

    nodes_a = _build_node_map(a)
    nodes_b = _build_node_map(b)
    shared_nodes = sorted(set(nodes_a.keys()) & set(nodes_b.keys()))

    concrete_diffs: List[Tuple[int, Tuple[int, int], Any, Any]] = []
    for node_idx in shared_nodes:
        pa = _build_pin_map(nodes_a[node_idx])
        pb = _build_pin_map(nodes_b[node_idx])
        for key in sorted(set(pa.keys()) & set(pb.keys())):
            ca = pa[key].get("concrete_index_of_concrete_int")
            cb = pb[key].get("concrete_index_of_concrete_int")
            if ca != cb:
                concrete_diffs.append((int(node_idx), key, ca, cb))

    print(f"pins concrete_index_of_concrete_int diffs: {len(concrete_diffs)}")
    if concrete_diffs:
        print("- diffs(head 30):")
        for node_idx, (kind, idx), ca, cb in concrete_diffs[:30]:
            print(f"  - node={node_idx} pin=({kind},{idx}) {label_a}={ca!r} {label_b}={cb!r}")


def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--a", dest="a_path", required=True, help="Graph IR JSON A")
    parser.add_argument("--b", dest="b_path", required=True, help="Graph IR JSON B")
    parser.add_argument("--label-a", dest="label_a", default="A", help="label for A")
    parser.add_argument("--label-b", dest="label_b", default="B", help="label for B")
    args = parser.parse_args(argv)

    a = _load_json(Path(args.a_path))
    b = _load_json(Path(args.b_path))
    if not isinstance(a, dict) or not isinstance(b, dict):
        raise TypeError("graph_ir json root must be dict")
    _diff_graph_ir(a, b, label_a=str(args.label_a), label_b=str(args.label_b))


if __name__ == "__main__":
    main()

