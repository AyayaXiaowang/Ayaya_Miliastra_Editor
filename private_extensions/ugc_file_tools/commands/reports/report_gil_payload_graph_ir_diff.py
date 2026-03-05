from __future__ import annotations

"""
report_gil_payload_graph_ir_diff.py

用途：
- 对比两份 `.gil` 的 payload（section10 / 10.1.1 NodeGraph blob）解析得到的 Graph IR，并输出差异报告，
  用于定位“同一份 Graph Code / 同一份节点图，经由游戏处理后的导出结果”与“工具直接处理结果”的差异。

对比维度（面向后续定位的基础设施）：
- graphs：A/B 两份 `.gil` 中各自包含哪些 graph_id_int（缺失/新增）
- edges：基于 **输入 pins（InFlow/InParam）上的 connects** 反推的边集合差异（missing/extra）
- pins：聚焦写回/导出最常见的漂移点：`type_id_int` / `concrete_index_of_concrete_int` / dict K/V

约束：
- 不使用 try/except；失败直接抛错（fail-fast / fail-closed）。
"""

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.graph.node_graph.gil_payload_graph_ir import (
    parse_gil_payload_node_graphs_to_graph_ir,
    read_gil_payload_bytes_and_container_meta,
)
from ugc_file_tools.node_data_index import resolve_default_node_data_index_path
from ugc_file_tools.output_paths import resolve_output_dir_path_in_out_dir


_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\\\|?*]')


def _sanitize_filename(name: str, *, max_length: int = 120) -> str:
    text = str(name or "").strip()
    if text == "":
        return "untitled"
    text = _INVALID_FILENAME_CHARS.sub("_", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > int(max_length):
        text = text[: int(max_length)].rstrip()
    if text == "":
        return "untitled"
    return text


def _ensure_directory(target_dir: Path) -> None:
    Path(target_dir).mkdir(parents=True, exist_ok=True)


def _write_json_file(target_path: Path, payload: Any) -> None:
    Path(target_path).parent.mkdir(parents=True, exist_ok=True)
    Path(target_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text_file(target_path: Path, text: str) -> None:
    Path(target_path).parent.mkdir(parents=True, exist_ok=True)
    Path(target_path).write_text(str(text or ""), encoding="utf-8")


@dataclass(frozen=True, slots=True)
class Edge:
    src_node: int
    src_kind: int
    src_index: int
    dst_node: int
    dst_kind: int
    dst_index: int

    def to_dict(self) -> Dict[str, int]:
        return {
            "src_node": int(self.src_node),
            "src_kind": int(self.src_kind),
            "src_index": int(self.src_index),
            "dst_node": int(self.dst_node),
            "dst_kind": int(self.dst_kind),
            "dst_index": int(self.dst_index),
        }


def _iter_node_dicts(graph_ir: Mapping[str, Any]) -> Iterable[Dict[str, Any]]:
    nodes = graph_ir.get("nodes")
    if isinstance(nodes, list):
        for n in list(nodes):
            if isinstance(n, dict):
                yield n


def _iter_pin_dicts(node: Mapping[str, Any]) -> Iterable[Dict[str, Any]]:
    pins = node.get("pins")
    if isinstance(pins, list):
        for p in list(pins):
            if isinstance(p, dict):
                yield p


def _node_index(node: Mapping[str, Any]) -> int:
    v = node.get("node_index_int")
    if isinstance(v, int):
        return int(v)
    return 0


def _node_type_id(node: Mapping[str, Any]) -> int:
    v = node.get("node_type_id_int")
    if isinstance(v, int):
        return int(v)
    return 0


def _node_type_name(node: Mapping[str, Any]) -> str:
    v = node.get("node_type_name")
    if isinstance(v, str):
        return v
    return ""


def _pin_key(pin: Mapping[str, Any]) -> Tuple[int, int]:
    kind = pin.get("kind_int")
    idx = pin.get("index_int")
    return (int(kind) if isinstance(kind, int) else 0, int(idx) if isinstance(idx, int) else 0)


def _summarize_value(value: Any) -> Any:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        if len(value) <= 200:
            return value
        return {"kind": "string", "length": len(value), "preview": value[:200]}
    if isinstance(value, list):
        head = value[:12]
        return {"kind": "list", "length": len(value), "head": [_summarize_value(x) for x in head]}
    if isinstance(value, dict):
        keys = [str(k) for k in value.keys()]
        keys_sorted = sorted(keys)
        return {"kind": "dict", "length": len(keys_sorted), "keys_head": keys_sorted[:30]}
    return {"kind": "unknown", "python_type": type(value).__name__}


def _pin_preview(pin: Mapping[str, Any]) -> Dict[str, Any]:
    connects = pin.get("connects")
    connects_count = len(connects) if isinstance(connects, list) else 0
    return {
        "type_id_int": pin.get("type_id_int"),
        "type_expr": pin.get("type_expr"),
        "concrete_index_of_concrete_int": pin.get("concrete_index_of_concrete_int"),
        "dict_key_type_int": pin.get("dict_key_type_int"),
        "dict_key_type_expr": pin.get("dict_key_type_expr"),
        "dict_value_type_int": pin.get("dict_value_type_int"),
        "dict_value_type_expr": pin.get("dict_value_type_expr"),
        "value_summary": _summarize_value(pin.get("value")),
        "connects_count": int(connects_count),
    }


def _graph_variable_preview(var: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "name": var.get("name"),
        "var_type_int": var.get("var_type_int"),
        "var_type_expr": var.get("var_type_expr"),
        "key_type_int": var.get("key_type_int"),
        "key_type_expr": var.get("key_type_expr"),
        "value_type_int": var.get("value_type_int"),
        "value_type_expr": var.get("value_type_expr"),
        "default_value_summary": _summarize_value(var.get("default_value")),
        "exposed": var.get("exposed"),
        "struct_id_int": var.get("struct_id_int"),
    }


def _iter_graph_variable_dicts(graph_ir: Mapping[str, Any]) -> Iterable[Dict[str, Any]]:
    raw = graph_ir.get("graph_variables")
    if isinstance(raw, list):
        for item in list(raw):
            if isinstance(item, dict):
                yield item


def _build_graph_variable_map(graph_ir: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for var in _iter_graph_variable_dicts(graph_ir):
        name = str(var.get("name") or "").strip()
        if name == "":
            continue
        if name in out:
            raise ValueError(f"duplicated graph variable name: {name!r}")
        out[name] = dict(var)
    return out


def _diff_graph_variables(
    a_graph_ir: Mapping[str, Any],
    b_graph_ir: Mapping[str, Any],
    *,
    label_a: str,
    label_b: str,
    max_diff_items: int,
) -> Dict[str, Any]:
    vars_a = _build_graph_variable_map(a_graph_ir)
    vars_b = _build_graph_variable_map(b_graph_ir)
    names_a = set(vars_a.keys())
    names_b = set(vars_b.keys())

    missing_in_a = sorted(list(names_b - names_a))
    missing_in_b = sorted(list(names_a - names_b))
    shared = sorted(list(names_a & names_b))

    mismatches_all: List[Dict[str, Any]] = []
    mismatch_field_counts: Dict[str, int] = {}

    for name in shared:
        va = vars_a[str(name)]
        vb = vars_b[str(name)]

        diffs: List[Dict[str, Any]] = []
        for field in (
            "var_type_int",
            "key_type_int",
            "value_type_int",
            "default_value",
            "exposed",
            "struct_id_int",
        ):
            av = va.get(field)
            bv = vb.get(field)
            if av == bv:
                continue
            diffs.append({"field": field, label_a: _summarize_value(av), label_b: _summarize_value(bv)})
            mismatch_field_counts[field] = int(mismatch_field_counts.get(field, 0)) + 1

        if not diffs:
            continue

        mismatches_all.append(
            {
                "name": str(name),
                "diffs": diffs,
                f"{label_a}_var": _graph_variable_preview(va),
                f"{label_b}_var": _graph_variable_preview(vb),
            }
        )

    if int(max_diff_items) > 0:
        mismatches = mismatches_all[: int(max_diff_items)]
    else:
        mismatches = mismatches_all

    mismatch_field_counts_sorted = [
        {"field": str(k), "count": int(v)}
        for k, v in sorted(mismatch_field_counts.items(), key=lambda kv: (-int(kv[1]), str(kv[0])))
    ]

    return {
        f"{label_a}_count": int(len(vars_a)),
        f"{label_b}_count": int(len(vars_b)),
        f"missing_in_{label_a}": list(missing_in_a),
        f"missing_in_{label_b}": list(missing_in_b),
        "mismatches_count": int(len(mismatches_all)),
        "mismatch_field_counts": mismatch_field_counts_sorted,
        "mismatches": list(mismatches),
        "truncated": {"mismatches": int(len(mismatches_all) - len(mismatches))},
    }


def _iter_edges_from_in_pins(graph_ir: Mapping[str, Any]) -> set[Edge]:
    """
    从 pins.connects 反推边集合（以 **输入 pin 的 connects** 为准）。

    Graph IR 约定（schema_version=2）：
    - kind_int=2 表示 InFlow（flow in）
    - kind_int=3 表示 InParam（data in）
    - connect.kind_int/index_int 表示远端 pin（OutFlow/OutParam）的 kind/index
    """
    edges: set[Edge] = set()
    for node in _iter_node_dicts(graph_ir):
        dst_node = _node_index(node)
        if int(dst_node) <= 0:
            continue
        for pin in _iter_pin_dicts(node):
            pin_kind = pin.get("kind_int")
            pin_index = pin.get("index_int")
            if not isinstance(pin_kind, int) or not isinstance(pin_index, int):
                continue
            if int(pin_kind) not in (2, 3):
                continue
            connects = pin.get("connects")
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
                src_kind = connect.get("kind_int")
                src_index = connect.get("index_int")
                if not isinstance(src_kind, int) or not isinstance(src_index, int):
                    continue
                edges.add(
                    Edge(
                        src_node=int(src_node),
                        src_kind=int(src_kind),
                        src_index=int(src_index),
                        dst_node=int(dst_node),
                        dst_kind=int(pin_kind),
                        dst_index=int(pin_index),
                    )
                )
    return edges


def _build_node_map(graph_ir: Mapping[str, Any]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for node in _iter_node_dicts(graph_ir):
        idx = _node_index(node)
        if int(idx) <= 0:
            continue
        out[int(idx)] = dict(node)
    return out


def _build_pin_map(node: Mapping[str, Any]) -> Dict[Tuple[int, int], Dict[str, Any]]:
    out: Dict[Tuple[int, int], Dict[str, Any]] = {}
    for p in _iter_pin_dicts(node):
        out[_pin_key(p)] = dict(p)
    return out


def _annotate_edges(edges: Sequence[Edge], *, node_map: Mapping[int, Mapping[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for e in edges:
        src_node = int(e.src_node)
        dst_node = int(e.dst_node)
        src = node_map.get(src_node, {})
        dst = node_map.get(dst_node, {})
        record = e.to_dict()
        record.update(
            {
                "src_node_type_id_int": _node_type_id(src),
                "src_node_type_name": _node_type_name(src),
                "dst_node_type_id_int": _node_type_id(dst),
                "dst_node_type_name": _node_type_name(dst),
            }
        )
        out.append(record)
    return out


def _build_top_missing_pin_stats(records: Sequence[Mapping[str, Any]], *, top_n: int = 12) -> Dict[str, Any]:
    by_node_type: Dict[Tuple[int, str], int] = {}
    by_node_type_and_kind: Dict[Tuple[int, str, int], int] = {}
    for r in records:
        type_id_int = r.get("node_type_id_int")
        type_name = str(r.get("node_type_name") or "")
        pin_kind_int = r.get("pin_kind_int")
        if not isinstance(type_id_int, int) or not isinstance(pin_kind_int, int):
            continue
        k1 = (int(type_id_int), str(type_name))
        by_node_type[k1] = int(by_node_type.get(k1, 0)) + 1
        k2 = (int(type_id_int), str(type_name), int(pin_kind_int))
        by_node_type_and_kind[k2] = int(by_node_type_and_kind.get(k2, 0)) + 1

    by_node_type_top = [
        {"node_type_id_int": int(tid), "node_type_name": str(name), "count": int(cnt)}
        for (tid, name), cnt in sorted(by_node_type.items(), key=lambda kv: (-int(kv[1]), int(kv[0][0]), str(kv[0][1])))[: int(top_n)]
    ]
    by_node_type_and_kind_top = [
        {"node_type_id_int": int(tid), "node_type_name": str(name), "pin_kind_int": int(kind), "count": int(cnt)}
        for (tid, name, kind), cnt in sorted(
            by_node_type_and_kind.items(),
            key=lambda kv: (-int(kv[1]), int(kv[0][0]), int(kv[0][2]), str(kv[0][1])),
        )[: int(top_n)]
    ]
    return {
        "by_node_type_top": by_node_type_top,
        "by_node_type_and_kind_top": by_node_type_and_kind_top,
    }


def _diff_graph_ir(
    a_graph_ir: Mapping[str, Any],
    b_graph_ir: Mapping[str, Any],
    *,
    label_a: str,
    label_b: str,
    max_diff_items: int,
) -> Dict[str, Any]:
    edges_a = _iter_edges_from_in_pins(a_graph_ir)
    edges_b = _iter_edges_from_in_pins(b_graph_ir)

    missing_in_a_all = sorted(
        list(edges_b - edges_a),
        key=lambda e: (e.src_node, e.src_kind, e.src_index, e.dst_node, e.dst_kind, e.dst_index),
    )
    missing_in_b_all = sorted(
        list(edges_a - edges_b),
        key=lambda e: (e.src_node, e.src_kind, e.src_index, e.dst_node, e.dst_kind, e.dst_index),
    )

    if int(max_diff_items) > 0:
        missing_in_a = missing_in_a_all[: int(max_diff_items)]
        missing_in_b = missing_in_b_all[: int(max_diff_items)]
    else:
        missing_in_a = missing_in_a_all
        missing_in_b = missing_in_b_all

    nodes_a = _build_node_map(a_graph_ir)
    nodes_b = _build_node_map(b_graph_ir)
    node_index_a = set(nodes_a.keys())
    node_index_b = set(nodes_b.keys())
    missing_nodes_in_a = sorted(list(node_index_b - node_index_a))
    missing_nodes_in_b = sorted(list(node_index_a - node_index_b))
    shared_nodes = sorted(list(node_index_a & node_index_b))

    node_type_id_mismatches: List[Dict[str, Any]] = []
    pin_field_mismatches_all: List[Dict[str, Any]] = []
    missing_pins_in_a_all: List[Dict[str, Any]] = []
    missing_pins_in_b_all: List[Dict[str, Any]] = []

    for node_idx in shared_nodes:
        na = nodes_a[int(node_idx)]
        nb = nodes_b[int(node_idx)]
        ta = _node_type_id(na)
        tb = _node_type_id(nb)
        if int(ta) != int(tb):
            node_type_id_mismatches.append(
                {
                    "node_index_int": int(node_idx),
                    f"{label_a}_node_type_id_int": int(ta),
                    f"{label_b}_node_type_id_int": int(tb),
                    f"{label_a}_node_type_name": _node_type_name(na),
                    f"{label_b}_node_type_name": _node_type_name(nb),
                }
            )

        pins_a = _build_pin_map(na)
        pins_b = _build_pin_map(nb)
        pk_a = set(pins_a.keys())
        pk_b = set(pins_b.keys())
        for pk in sorted(list(pk_b - pk_a), key=lambda x: (int(x[0]), int(x[1]))):
            pb = pins_b[pk]
            missing_pins_in_a_all.append(
                {
                    "node_index_int": int(node_idx),
                    "node_type_id_int": int(tb),
                    "node_type_name": _node_type_name(nb),
                    "pin_kind_int": int(pk[0]),
                    "pin_index_int": int(pk[1]),
                    f"{label_b}_pin": _pin_preview(pb),
                }
            )
        for pk in sorted(list(pk_a - pk_b), key=lambda x: (int(x[0]), int(x[1]))):
            pa = pins_a[pk]
            missing_pins_in_b_all.append(
                {
                    "node_index_int": int(node_idx),
                    "node_type_id_int": int(ta),
                    "node_type_name": _node_type_name(na),
                    "pin_kind_int": int(pk[0]),
                    "pin_index_int": int(pk[1]),
                    f"{label_a}_pin": _pin_preview(pa),
                }
            )

        shared_pins = sorted(list(pk_a & pk_b), key=lambda x: (int(x[0]), int(x[1])))
        for pk in shared_pins:
            pa = pins_a[pk]
            pb = pins_b[pk]

            diffs: List[Dict[str, Any]] = []
            for field in (
                "type_id_int",
                "concrete_index_of_concrete_int",
                "dict_key_type_int",
                "dict_value_type_int",
            ):
                av = pa.get(field)
                bv = pb.get(field)
                if av == bv:
                    continue
                diffs.append({"field": field, label_a: av, label_b: bv})

            if not diffs:
                continue

            pin_field_mismatches_all.append(
                {
                    "node_index_int": int(node_idx),
                    "node_type_id_int": int(tb),
                    "node_type_name": _node_type_name(nb),
                    "pin_kind_int": int(pk[0]),
                    "pin_index_int": int(pk[1]),
                    "diffs": diffs,
                    f"{label_a}_pin": _pin_preview(pa),
                    f"{label_b}_pin": _pin_preview(pb),
                }
            )

    if int(max_diff_items) > 0:
        pin_field_mismatches = pin_field_mismatches_all[: int(max_diff_items)]
        missing_pins_in_a = missing_pins_in_a_all[: int(max_diff_items)]
        missing_pins_in_b = missing_pins_in_b_all[: int(max_diff_items)]
    else:
        pin_field_mismatches = pin_field_mismatches_all
        missing_pins_in_a = missing_pins_in_a_all
        missing_pins_in_b = missing_pins_in_b_all

    graph_variables_diff = _diff_graph_variables(
        a_graph_ir,
        b_graph_ir,
        label_a=str(label_a),
        label_b=str(label_b),
        max_diff_items=int(max_diff_items),
    )

    return {
        "edges": {
            f"{label_a}_count": int(len(edges_a)),
            f"{label_b}_count": int(len(edges_b)),
            f"missing_in_{label_a}_count": int(len(missing_in_a_all)),
            f"missing_in_{label_b}_count": int(len(missing_in_b_all)),
            f"missing_in_{label_a}": [e.to_dict() for e in missing_in_a],
            f"missing_in_{label_b}": [e.to_dict() for e in missing_in_b],
            f"missing_in_{label_a}_with_types": _annotate_edges(missing_in_a, node_map=nodes_b),
            f"missing_in_{label_b}_with_types": _annotate_edges(missing_in_b, node_map=nodes_a),
            "truncated": {
                f"missing_in_{label_a}": int(len(missing_in_a_all) - len(missing_in_a)),
                f"missing_in_{label_b}": int(len(missing_in_b_all) - len(missing_in_b)),
            },
        },
        "nodes": {
            f"{label_a}_node_count": int(len(nodes_a)),
            f"{label_b}_node_count": int(len(nodes_b)),
            f"missing_in_{label_a}_nodes": list(missing_nodes_in_a),
            f"missing_in_{label_b}_nodes": list(missing_nodes_in_b),
            "node_type_id_mismatches": list(node_type_id_mismatches),
        },
        "pins": {
            "pin_field_mismatches_count": int(len(pin_field_mismatches_all)),
            "pin_field_mismatches": list(pin_field_mismatches),
            "missing_pins_in_a_count": int(len(missing_pins_in_a_all)),
            "missing_pins_in_b_count": int(len(missing_pins_in_b_all)),
            "missing_pins_in_a": list(missing_pins_in_a),
            "missing_pins_in_b": list(missing_pins_in_b),
            "missing_pins_in_a_stats": _build_top_missing_pin_stats(missing_pins_in_a_all),
            "missing_pins_in_b_stats": _build_top_missing_pin_stats(missing_pins_in_b_all),
            "truncated": {
                "pin_field_mismatches": int(len(pin_field_mismatches_all) - len(pin_field_mismatches)),
                "missing_pins_in_a": int(len(missing_pins_in_a_all) - len(missing_pins_in_a)),
                "missing_pins_in_b": int(len(missing_pins_in_b_all) - len(missing_pins_in_b)),
            },
        },
        "graph_variables": graph_variables_diff,
    }


def build_report(
    a_gil_file: Path,
    b_gil_file: Path,
    *,
    output_dir: Path,
    node_data_index_path: Path,
    graph_ids: Optional[List[int]] = None,
    max_depth: int = 16,
    max_diff_items: int = 200,
    label_a: str = "a",
    label_b: str = "b",
    dump_graph_ir: bool = True,
) -> Dict[str, Any]:
    a_gil_file = Path(a_gil_file).resolve()
    b_gil_file = Path(b_gil_file).resolve()
    node_data_index_path = Path(node_data_index_path).resolve()

    if not a_gil_file.is_file():
        raise FileNotFoundError(str(a_gil_file))
    if not b_gil_file.is_file():
        raise FileNotFoundError(str(b_gil_file))
    if not node_data_index_path.is_file():
        raise FileNotFoundError(str(node_data_index_path))

    output_dir = resolve_output_dir_path_in_out_dir(Path(output_dir), default_dir_name="gil_payload_graph_ir_diff")
    _ensure_directory(output_dir)

    a_dir = output_dir / f"{label_a}_graphs"
    b_dir = output_dir / f"{label_b}_graphs"
    diffs_dir = output_dir / "diffs"
    _ensure_directory(a_dir)
    _ensure_directory(b_dir)
    _ensure_directory(diffs_dir)

    _payload_a, container_a = read_gil_payload_bytes_and_container_meta(gil_file_path=a_gil_file)
    _payload_b, container_b = read_gil_payload_bytes_and_container_meta(gil_file_path=b_gil_file)

    selected_graph_id_set: Optional[set[int]] = None
    if graph_ids:
        selected_graph_id_set = {int(x) for x in graph_ids if isinstance(x, int)}

    parsed_a = parse_gil_payload_node_graphs_to_graph_ir(
        gil_file_path=a_gil_file,
        node_data_index_path=node_data_index_path,
        graph_ids=(sorted(list(selected_graph_id_set)) if selected_graph_id_set is not None else None),
        max_depth=int(max_depth),
    )
    parsed_b = parse_gil_payload_node_graphs_to_graph_ir(
        gil_file_path=b_gil_file,
        node_data_index_path=node_data_index_path,
        graph_ids=(sorted(list(selected_graph_id_set)) if selected_graph_id_set is not None else None),
        max_depth=int(max_depth),
    )

    graphs_a: Dict[int, Dict[str, Any]] = {}
    graphs_b: Dict[int, Dict[str, Any]] = {}

    for item in parsed_a:
        graph_id_int = int(item.graph_id_int)
        if graph_id_int in graphs_a:
            raise ValueError(f"duplicated graph_id_int in {label_a}: {graph_id_int}")
        graphs_a[graph_id_int] = {
            "graph_id_int": graph_id_int,
            "graph_name": str(item.graph_name or "").strip(),
            "group_index": int(item.group_index),
            "entry_index": int(item.entry_index),
            "blob_bytes_len": int(item.blob_bytes_len),
            "graph_ir": dict(item.graph_ir),
        }

    for item in parsed_b:
        graph_id_int = int(item.graph_id_int)
        if graph_id_int in graphs_b:
            raise ValueError(f"duplicated graph_id_int in {label_b}: {graph_id_int}")
        graphs_b[graph_id_int] = {
            "graph_id_int": graph_id_int,
            "graph_name": str(item.graph_name or "").strip(),
            "group_index": int(item.group_index),
            "entry_index": int(item.entry_index),
            "blob_bytes_len": int(item.blob_bytes_len),
            "graph_ir": dict(item.graph_ir),
        }

    graph_ids_all = sorted(set(graphs_a.keys()) | set(graphs_b.keys()))

    per_graph_index: List[Dict[str, Any]] = []
    summary_lines: List[str] = []
    summary_lines.append("## GIL payload Graph IR diff 报告")
    summary_lines.append("")
    summary_lines.append(f"- {label_a}: `{a_gil_file}`")
    summary_lines.append(f"- {label_b}: `{b_gil_file}`")
    summary_lines.append(f"- node_data_index: `{node_data_index_path}`")
    summary_lines.append(f"- max_depth: {int(max_depth)}")
    summary_lines.append(f"- max_diff_items: {int(max_diff_items)}（0=不截断）")
    summary_lines.append("")

    missing_graphs_in_a = sorted(list(set(graphs_b.keys()) - set(graphs_a.keys())))
    missing_graphs_in_b = sorted(list(set(graphs_a.keys()) - set(graphs_b.keys())))
    if missing_graphs_in_a or missing_graphs_in_b:
        summary_lines.append("### graphs 缺失/新增")
        summary_lines.append("")
        if missing_graphs_in_a:
            summary_lines.append(f"- missing_in_{label_a}: {missing_graphs_in_a}")
        if missing_graphs_in_b:
            summary_lines.append(f"- missing_in_{label_b}: {missing_graphs_in_b}")
        summary_lines.append("")

    for gid in graph_ids_all:
        ga = graphs_a.get(int(gid))
        gb = graphs_b.get(int(gid))
        if ga is None or gb is None:
            per_graph_index.append(
                {
                    "graph_id_int": int(gid),
                    "graph_name": (gb.get("graph_name") if gb is not None else ga.get("graph_name") if ga is not None else ""),
                    "status": "missing_graph",
                    f"missing_in_{label_a}": bool(ga is None),
                    f"missing_in_{label_b}": bool(gb is None),
                }
            )
            continue

        graph_name = str(gb.get("graph_name") or ga.get("graph_name") or "").strip()
        safe_stem = _sanitize_filename(f"gil_payload_ir_diff_{gid}_{graph_name}", max_length=140)

        a_graph_ir = dict(ga["graph_ir"])
        b_graph_ir = dict(gb["graph_ir"])

        if dump_graph_ir:
            a_graph_path = a_dir / f"{safe_stem}.a.graph_ir.json"
            b_graph_path = b_dir / f"{safe_stem}.b.graph_ir.json"
            _write_json_file(
                a_graph_path,
                {
                    **a_graph_ir,
                    "source_gil_file": str(a_gil_file),
                    "gil_container": container_a,
                    "node_data_index_path": str(node_data_index_path),
                    "decode_max_depth": int(max_depth),
                    "node_graph_blob_meta": {
                        "group_index": int(ga["group_index"]),
                        "entry_index": int(ga["entry_index"]),
                        "blob_bytes_len": int(ga["blob_bytes_len"]),
                    },
                },
            )
            _write_json_file(
                b_graph_path,
                {
                    **b_graph_ir,
                    "source_gil_file": str(b_gil_file),
                    "gil_container": container_b,
                    "node_data_index_path": str(node_data_index_path),
                    "decode_max_depth": int(max_depth),
                    "node_graph_blob_meta": {
                        "group_index": int(gb["group_index"]),
                        "entry_index": int(gb["entry_index"]),
                        "blob_bytes_len": int(gb["blob_bytes_len"]),
                    },
                },
            )
        else:
            a_graph_path = None
            b_graph_path = None

        diff = _diff_graph_ir(
            a_graph_ir,
            b_graph_ir,
            label_a=str(label_a),
            label_b=str(label_b),
            max_diff_items=int(max_diff_items),
        )

        diff_path = diffs_dir / f"{safe_stem}.diff.json"
        _write_json_file(
            diff_path,
            {
                "graph_id_int": int(gid),
                "graph_name": str(graph_name),
                label_a: {
                    "group_index": int(ga["group_index"]),
                    "entry_index": int(ga["entry_index"]),
                    "blob_bytes_len": int(ga["blob_bytes_len"]),
                    "graph_ir_json": str(a_graph_path) if a_graph_path is not None else None,
                },
                label_b: {
                    "group_index": int(gb["group_index"]),
                    "entry_index": int(gb["entry_index"]),
                    "blob_bytes_len": int(gb["blob_bytes_len"]),
                    "graph_ir_json": str(b_graph_path) if b_graph_path is not None else None,
                },
                "diff": diff,
            },
        )

        edges = diff.get("edges") or {}
        pins = diff.get("pins") or {}
        graph_variables = diff.get("graph_variables") or {}
        per_graph_index.append(
            {
                "graph_id_int": int(gid),
                "graph_name": str(graph_name),
                "status": "ok",
                f"{label_a}_graph_ir_json": str(a_graph_path) if a_graph_path is not None else None,
                f"{label_b}_graph_ir_json": str(b_graph_path) if b_graph_path is not None else None,
                "diff_json": str(diff_path.relative_to(output_dir)).replace("\\", "/"),
                "edges": {
                    f"{label_a}_count": edges.get(f"{label_a}_count"),
                    f"{label_b}_count": edges.get(f"{label_b}_count"),
                    f"missing_in_{label_a}_count": edges.get(f"missing_in_{label_a}_count"),
                    f"missing_in_{label_b}_count": edges.get(f"missing_in_{label_b}_count"),
                },
                "pins": {
                    "pin_field_mismatches_count": pins.get("pin_field_mismatches_count"),
                    "missing_pins_in_a_count": pins.get("missing_pins_in_a_count"),
                    "missing_pins_in_b_count": pins.get("missing_pins_in_b_count"),
                },
                "graph_variables": {
                    f"{label_a}_count": graph_variables.get(f"{label_a}_count"),
                    f"{label_b}_count": graph_variables.get(f"{label_b}_count"),
                    f"missing_in_{label_a}_count": len(graph_variables.get(f"missing_in_{label_a}") or []),
                    f"missing_in_{label_b}_count": len(graph_variables.get(f"missing_in_{label_b}") or []),
                    "mismatches_count": graph_variables.get("mismatches_count"),
                },
            }
        )

        summary_lines.append(f"### graph {gid}: {graph_name}")
        summary_lines.append("")
        summary_lines.append(
            f"- edges: {label_a}={edges.get(f'{label_a}_count')} {label_b}={edges.get(f'{label_b}_count')} "
            f"missing_in_{label_a}={edges.get(f'missing_in_{label_a}_count')} "
            f"missing_in_{label_b}={edges.get(f'missing_in_{label_b}_count')}"
        )
        summary_lines.append(
            f"- pins: pin_field_mismatches={pins.get('pin_field_mismatches_count')} "
            f"missing_pins_in_{label_a}={pins.get('missing_pins_in_a_count')} "
            f"missing_pins_in_{label_b}={pins.get('missing_pins_in_b_count')}"
        )
        summary_lines.append(
            f"- graph_variables: {label_a}={graph_variables.get(f'{label_a}_count')} {label_b}={graph_variables.get(f'{label_b}_count')} "
            f"missing_in_{label_a}={len(graph_variables.get(f'missing_in_{label_a}') or [])} "
            f"missing_in_{label_b}={len(graph_variables.get(f'missing_in_{label_b}') or [])} "
            f"mismatches={graph_variables.get('mismatches_count')}"
        )

        stats_a = (pins.get("missing_pins_in_a_stats") or {}).get("by_node_type_top") or []
        stats_b = (pins.get("missing_pins_in_b_stats") or {}).get("by_node_type_top") or []
        if stats_a:
            top_a = "; ".join(
                [
                    f"{str(it.get('node_type_name') or '')}({it.get('node_type_id_int')}):{it.get('count')}"
                    for it in list(stats_a)[:6]
                    if isinstance(it, dict)
                ]
            )
            if top_a:
                summary_lines.append(f"- missing_pins_in_{label_a}_top: {top_a}")
        if stats_b:
            top_b = "; ".join(
                [
                    f"{str(it.get('node_type_name') or '')}({it.get('node_type_id_int')}):{it.get('count')}"
                    for it in list(stats_b)[:6]
                    if isinstance(it, dict)
                ]
            )
            if top_b:
                summary_lines.append(f"- missing_pins_in_{label_b}_top: {top_b}")
        summary_lines.append(f"- diff_json: `{diff_path}`")
        summary_lines.append("")

    index_path = output_dir / "index.json"
    _write_json_file(index_path, per_graph_index)

    report_path = output_dir / "report.json"
    _write_json_file(
        report_path,
        {
            "label_a": str(label_a),
            "label_b": str(label_b),
            "a_gil_file": str(a_gil_file),
            "b_gil_file": str(b_gil_file),
            "container_meta": {str(label_a): container_a, str(label_b): container_b},
            "node_data_index_path": str(node_data_index_path),
            "max_depth": int(max_depth),
            "max_diff_items": int(max_diff_items),
            "dump_graph_ir": bool(dump_graph_ir),
            "selected_graph_ids": (sorted(list(selected_graph_id_set)) if selected_graph_id_set is not None else None),
            "graphs": per_graph_index,
            "missing_graphs": {
                f"missing_in_{label_a}": missing_graphs_in_a,
                f"missing_in_{label_b}": missing_graphs_in_b,
            },
        },
    )

    summary_md_path = output_dir / "summary.md"
    _write_text_file(summary_md_path, "\n".join(summary_lines) + "\n")

    claude_path = output_dir / "claude.md"
    _write_text_file(
        claude_path,
        "\n".join(
            [
                "## 目录用途",
                "- 存放 `report_gil_payload_graph_ir_diff` 生成的对照报告：对比两份 `.gil` 的 payload NodeGraph Graph IR（edges/pins），用于定位“游戏处理后导出 vs 工具直接处理”的结构差异。",
                "",
                "## 当前状态",
                f"- 当前包含 {len(per_graph_index)} 张图的 diff 结果（包含缺失图条目）。",
                f"- `{label_a}_graphs/` 与 `{label_b}_graphs/`：两侧导出的 Graph IR JSON（证据快照；可选关闭 dump）。",
                "- `diffs/`：每张图的差异 JSON。",
                "- `index.json`：图列表索引（用于脚本化读取）。",
                "- `summary.md`：可读摘要。",
                "",
                "## 注意事项",
                "- edges 差异基于输入 pins 的 connects 反推（对齐常见 `.gil` 结构：连线信息主要挂在 InFlow/InParam）。",
                "- 本目录不记录修改历史，仅保持用途/状态/注意事项的实时描述。",
                "",
                "---",
                "注意：本文件不记录任何修改历史。请始终保持对“目录用途、当前状态、注意事项”的实时描述。",
                "",
            ]
        ),
    )

    return {
        "output_dir": str(output_dir),
        "index": str(index_path),
        "report": str(report_path),
        "summary_md": str(summary_md_path),
        "graphs_count": len(per_graph_index),
    }


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    argument_parser = argparse.ArgumentParser(
        description="对比两份 .gil 的 payload NodeGraph Graph IR（edges/pins），输出差异报告（写入 ugc_file_tools/out/）。"
    )
    argument_parser.add_argument("--a-gil", dest="a_gil_file", required=True, help="输入 .gil A 路径")
    argument_parser.add_argument("--b-gil", dest="b_gil_file", required=True, help="输入 .gil B 路径")
    argument_parser.add_argument(
        "--output-dir",
        dest="output_dir",
        default="gil_payload_graph_ir_diff",
        help="输出目录（默认：gil_payload_graph_ir_diff；实际会被收口到 ugc_file_tools/out/ 下）。",
    )
    argument_parser.add_argument(
        "--node-data-index",
        dest="node_data_index",
        default=str(resolve_default_node_data_index_path()),
        help="节点数据索引 index.json 路径（默认：ugc_file_tools/node_data/index.json）",
    )
    argument_parser.add_argument(
        "--graph-id",
        dest="graph_ids",
        action="append",
        type=int,
        default=[],
        help="仅对比指定 graph_id_int（可重复传多次）。不传则对比两侧并集，并在报告中标记缺失图。",
    )
    argument_parser.add_argument(
        "--max-depth",
        dest="max_depth",
        type=int,
        default=16,
        help="NodeGraph blob 深度解码上限（默认 16）。",
    )
    argument_parser.add_argument(
        "--max-diff-items",
        dest="max_diff_items",
        type=int,
        default=200,
        help="每张图的 diff 明细最大条目数（默认 200；0=不截断，可能产生很大的报告）。",
    )
    argument_parser.add_argument(
        "--label-a",
        dest="label_a",
        default="a",
        help="报告中 A 的标签（默认 a）。",
    )
    argument_parser.add_argument(
        "--label-b",
        dest="label_b",
        default="b",
        help="报告中 B 的标签（默认 b）。",
    )
    argument_parser.add_argument(
        "--no-dump-graph-ir",
        dest="no_dump_graph_ir",
        action="store_true",
        help="不落盘两侧 Graph IR JSON（只落盘 diff/report/index/summary）。",
    )

    arguments = argument_parser.parse_args(list(argv) if argv is not None else None)

    result = build_report(
        Path(arguments.a_gil_file),
        Path(arguments.b_gil_file),
        output_dir=Path(arguments.output_dir),
        node_data_index_path=Path(arguments.node_data_index),
        graph_ids=list(arguments.graph_ids or []),
        max_depth=int(arguments.max_depth),
        max_diff_items=int(arguments.max_diff_items),
        label_a=str(arguments.label_a),
        label_b=str(arguments.label_b),
        dump_graph_ir=(not bool(arguments.no_dump_graph_ir)),
    )

    print("=" * 80)
    print("GIL payload Graph IR diff 报告生成完成：")
    print(f"- output_dir: {result.get('output_dir')}")
    print(f"- report: {result.get('report')}")
    print(f"- index: {result.get('index')}")
    print(f"- summary_md: {result.get('summary_md')}")
    print(f"- graphs_count: {result.get('graphs_count')}")
    print("=" * 80)


if __name__ == "__main__":
    main()

