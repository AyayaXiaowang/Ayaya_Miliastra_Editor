from __future__ import annotations

from typing import Any, Dict, List, Optional

from ugc_file_tools.gia.varbase_semantics import (
    FieldMap,
    as_list,
    coerce_bool_value,
    extract_varbase_value,
    get_field,
    get_float32_field,
    get_int_field,
    get_message_field,
    get_utf8_field,
    iter_message_nodes,
)


def infer_graph_scope_from_id_int(graph_id_int: int) -> str:
    """
    与 `export_graph_ir_from_package.py`/`parse_gia_to_graph_ir.py` 的口径保持一致：
    - 0x40000000: server
    - 0x40800000: client
    - 0x60000000: server（node_def / accessories 子图常见取值；仍按 server 口径解析端口名与类型）
    - 0x60800000: client（对称约定；若未来出现则按 client 口径解析）
    """
    masked_value = int(graph_id_int) & 0xFF800000
    if masked_value == 0x40000000:
        return "server"
    if masked_value == 0x40800000:
        return "client"
    if masked_value == 0x60000000:
        return "server"
    if masked_value == 0x60800000:
        return "client"
    return "unknown"


def parse_node_pin_index(index_message: FieldMap) -> Dict[str, Any]:
    client_exec_id = None
    node_id_msg = get_message_field(index_message, 100)
    if isinstance(node_id_msg, dict):
        client_exec_id = get_int_field(node_id_msg, 1)
    return {
        "kind_int": get_int_field(index_message, 1) or 0,
        "index_int": get_int_field(index_message, 2) or 0,
        "client_exec_node_id_int": int(client_exec_id) if isinstance(client_exec_id, int) else None,
    }


def parse_comment_message(comment_message: FieldMap) -> Dict[str, Any]:
    return {
        "content": get_utf8_field(comment_message, 1) or "",
        "x": get_float32_field(comment_message, 2),
        "y": get_float32_field(comment_message, 3),
    }


def parse_node_graph_id_message(id_message: FieldMap) -> Dict[str, Any]:
    return {
        "class_int": get_int_field(id_message, 1),
        "type_int": get_int_field(id_message, 2),
        "kind_int": get_int_field(id_message, 3),
        "id_int": get_int_field(id_message, 5),
    }


def parse_graph_affiliation_info_message(info_message: FieldMap) -> Dict[str, Any]:
    source = get_message_field(info_message, 1) or {}
    struct_item = get_message_field(info_message, 100) or {}
    struct_id_int = get_int_field(struct_item, 1)
    return {
        "source": parse_node_graph_id_message(source) if source else None,
        "type_xxx_int": get_int_field(info_message, 2),
        "always_one_xxxx_int": get_int_field(info_message, 3),
        "struct_id_int": int(struct_id_int) if isinstance(struct_id_int, int) else None,
    }


def parse_graph_affiliation_message(affiliation_message: FieldMap) -> Dict[str, Any]:
    info = get_message_field(affiliation_message, 1) or {}
    tp = get_message_field(affiliation_message, 2) or {}
    return {
        "info": parse_graph_affiliation_info_message(info) if info else None,
        "type_int": get_int_field(tp, 1),
    }


def parse_composite_pin_message(pin_message: FieldMap) -> Dict[str, Any]:
    outer = get_message_field(pin_message, 1) or {}
    inner = get_message_field(pin_message, 3) or {}
    inner2 = get_message_field(pin_message, 4) or {}
    return {
        "outer_pin": parse_node_pin_index(outer) if outer else None,
        "inner_node_id_int": get_int_field(pin_message, 2),
        "inner_pin": parse_node_pin_index(inner) if inner else None,
        "inner_pin2": parse_node_pin_index(inner2) if inner2 else None,
    }


def parse_graph_variable_message(
    graph_variable_message: FieldMap,
    *,
    type_entry_by_id: Dict[int, Dict[str, Any]],
) -> Dict[str, Any]:
    name = get_utf8_field(graph_variable_message, 2) or ""
    var_type_int = get_int_field(graph_variable_message, 3)
    key_type_int = get_int_field(graph_variable_message, 7)
    value_type_int = get_int_field(graph_variable_message, 8)

    type_entry = type_entry_by_id.get(int(var_type_int)) if isinstance(var_type_int, int) else None
    type_expr = str(type_entry.get("Expression") or "").strip() if isinstance(type_entry, dict) else ""

    key_entry = type_entry_by_id.get(int(key_type_int)) if isinstance(key_type_int, int) else None
    key_type_expr = str(key_entry.get("Expression") or "").strip() if isinstance(key_entry, dict) else ""

    val_entry = type_entry_by_id.get(int(value_type_int)) if isinstance(value_type_int, int) else None
    value_type_expr = str(val_entry.get("Expression") or "").strip() if isinstance(val_entry, dict) else ""

    values_message = get_message_field(graph_variable_message, 4) or {}
    extracted_value: Any = extract_varbase_value(values_message)
    if isinstance(var_type_int, int) and int(var_type_int) == 4:
        extracted_value = coerce_bool_value(extracted_value)

    exposed_int = get_int_field(graph_variable_message, 5)
    struct_id_int = get_int_field(graph_variable_message, 6)

    return {
        "name": name,
        "var_type_int": int(var_type_int) if isinstance(var_type_int, int) else None,
        "var_type_expr": type_expr,
        "key_type_int": int(key_type_int) if isinstance(key_type_int, int) else None,
        "key_type_expr": key_type_expr,
        "value_type_int": int(value_type_int) if isinstance(value_type_int, int) else None,
        "value_type_expr": value_type_expr,
        "default_value": extracted_value,
        "exposed": bool(int(exposed_int)) if isinstance(exposed_int, int) else None,
        "struct_id_int": int(struct_id_int) if isinstance(struct_id_int, int) else None,
    }


def parse_node_connections(connections_node: Any) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for connection_msg in iter_message_nodes(connections_node):
        remote_node_index_int = get_int_field(connection_msg, 1)
        connect = get_message_field(connection_msg, 2) or {}
        connect2 = get_message_field(connection_msg, 3) or {}
        results.append(
            {
                "remote_node_index_int": int(remote_node_index_int) if isinstance(remote_node_index_int, int) else None,
                "connect": parse_node_pin_index(connect),
                "connect2": parse_node_pin_index(connect2) if connect2 else None,
            }
        )
    return results


def _unwrap_concrete_base_varbase(varbase_message: FieldMap) -> FieldMap:
    """
    `.gia` 的端口 VarBase 可能被 ConcreteBase(10000) 包裹（反射/泛型端口常见）。

    部分类型信息（例如 MapBase 的 key/value VarType）位于 inner VarBase 的 ItemType 中，
    因此在读取这些信息前需要先解开 ConcreteBase。
    """
    cur = varbase_message if isinstance(varbase_message, dict) else {}
    while True:
        cls = get_int_field(cur, 1)
        if not isinstance(cls, int) or int(cls) != 10000:
            return cur
        concrete = get_message_field(cur, 110)
        if concrete is None:
            return cur
        inner = get_message_field(concrete, 2)
        if inner is None:
            return cur
        cur = inner


def parse_node_pin(
    pin_message: FieldMap,
    *,
    type_entry_by_id: Dict[int, Dict[str, Any]],
) -> Dict[str, Any]:
    i1 = get_message_field(pin_message, 1) or {}
    i2 = get_message_field(pin_message, 2) or {}
    i1_parsed = parse_node_pin_index(i1) if i1 else {"kind_int": 0, "index_int": 0, "client_exec_node_id_int": None}
    kind_int = int(i1_parsed.get("kind_int") or 0)
    index_int = int(i1_parsed.get("index_int") or 0)

    type_id_int = get_int_field(pin_message, 4)
    type_entry = type_entry_by_id.get(int(type_id_int)) if isinstance(type_id_int, int) else None
    type_expr = str(type_entry.get("Expression") or "").strip() if isinstance(type_entry, dict) else ""

    value_message = get_message_field(pin_message, 3) or {}
    varbase_cls_int = get_int_field(value_message, 1)
    concrete_index_of_concrete_int: Optional[int] = None
    concrete_inner_cls_int: Optional[int] = None
    if isinstance(varbase_cls_int, int) and int(varbase_cls_int) == 10000:
        # ConcreteBase: record indexOfConcrete + inner VarBase cls for diagnostics
        concrete_msg = get_message_field(value_message, 110) or {}
        idx = get_int_field(concrete_msg, 1)
        if isinstance(idx, int):
            concrete_index_of_concrete_int = int(idx)
        inner_msg = get_message_field(concrete_msg, 2)
        if isinstance(inner_msg, dict):
            inner_cls = get_int_field(inner_msg, 1)
            if isinstance(inner_cls, int):
                concrete_inner_cls_int = int(inner_cls)
    extracted_value: Any = extract_varbase_value(value_message)
    if type_id_int == 4:
        extracted_value = coerce_bool_value(extracted_value)

    dict_key_type_int: Optional[int] = None
    dict_value_type_int: Optional[int] = None
    dict_key_type_expr: str = ""
    dict_value_type_expr: str = ""
    if isinstance(type_id_int, int) and int(type_id_int) == 27:
        target_varbase = _unwrap_concrete_base_varbase(value_message)
        item_type = get_message_field(target_varbase, 4) or {}
        type_server = get_message_field(item_type, 100) or {}
        pair_items = get_message_field(type_server, 101) or {}
        dict_key_type_int = get_int_field(pair_items, 1)
        dict_value_type_int = get_int_field(pair_items, 2)
        if isinstance(dict_key_type_int, int):
            key_entry = type_entry_by_id.get(int(dict_key_type_int))
            if isinstance(key_entry, dict):
                dict_key_type_expr = str(key_entry.get("Expression") or "").strip()
        if isinstance(dict_value_type_int, int):
            val_entry = type_entry_by_id.get(int(dict_value_type_int))
            if isinstance(val_entry, dict):
                dict_value_type_expr = str(val_entry.get("Expression") or "").strip()

    connects = parse_node_connections(get_field(pin_message, 5))

    client_exec_node_msg = get_message_field(pin_message, 6)
    composite_pin_index_int = get_int_field(pin_message, 7)

    return {
        "kind_int": int(kind_int),
        "index_int": int(index_int),
        "i1_client_exec_node_id_int": i1_parsed.get("client_exec_node_id_int"),
        "type_id_int": int(type_id_int) if isinstance(type_id_int, int) else None,
        "type_expr": type_expr,
        "value": extracted_value,
        # diagnostics: preserve ConcreteBase wrapper info (generic/reflective pins often rely on it)
        "varbase_cls_int": int(varbase_cls_int) if isinstance(varbase_cls_int, int) else None,
        "concrete_index_of_concrete_int": concrete_index_of_concrete_int,
        "concrete_inner_cls_int": concrete_inner_cls_int,
        "dict_key_type_int": int(dict_key_type_int) if isinstance(dict_key_type_int, int) else None,
        "dict_value_type_int": int(dict_value_type_int) if isinstance(dict_value_type_int, int) else None,
        "dict_key_type_expr": str(dict_key_type_expr),
        "dict_value_type_expr": str(dict_value_type_expr),
        "connects": connects,
        "i2": parse_node_pin_index(i2) if i2 else None,
        "client_exec_node": parse_node_pin_index(client_exec_node_msg) if isinstance(client_exec_node_msg, dict) else None,
        "composite_pin_index_int": int(composite_pin_index_int) if isinstance(composite_pin_index_int, int) else None,
    }


def parse_edges_from_pins(*, node_index_int: int, pins: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    对齐 `gia.proto`：
    - OutFlow(kind=2) 的 connects：id=to_node_index，connect.index=to_pin_index → flow edge
    - InParam(kind=3) 的 connects：id=from_node_index，connect.index=from_pin_index → data edge
    """
    edges: List[Dict[str, Any]] = []
    for pin in pins:
        kind_int = int(pin.get("kind_int") or 0)
        self_index_int = int(pin.get("index_int") or 0)
        for connection in pin.get("connects") or []:
            remote_node_index_int = connection.get("remote_node_index_int")
            connect = connection.get("connect") or {}
            remote_pin_index_int = int(connect.get("index_int") or 0)
            if remote_node_index_int is None:
                continue
            if kind_int == 2:
                edges.append(
                    {
                        "edge_kind": "flow",
                        "src_node_index_int": int(node_index_int),
                        "src_port_index_int": int(self_index_int),
                        "dst_node_index_int": int(remote_node_index_int),
                        "dst_port_index_int": int(remote_pin_index_int),
                    }
                )
            elif kind_int == 3:
                edges.append(
                    {
                        "edge_kind": "data",
                        "src_node_index_int": int(remote_node_index_int),
                        "src_port_index_int": int(remote_pin_index_int),
                        "dst_node_index_int": int(node_index_int),
                        "dst_port_index_int": int(self_index_int),
                    }
                )
    return edges


def parse_node_property(message: FieldMap) -> Dict[str, Any]:
    return {
        "class_int": get_int_field(message, 1),
        "type_int": get_int_field(message, 2),
        "kind_int": get_int_field(message, 3),
        "node_id_int": get_int_field(message, 5),
    }


def parse_graph_node(
    node_message: FieldMap,
    *,
    node_entry_by_id: Dict[int, Dict[str, Any]],
    type_entry_by_id: Dict[int, Dict[str, Any]],
) -> Dict[str, Any]:
    node_index_int = get_int_field(node_message, 1) or 0
    generic_id_msg = get_message_field(node_message, 2) or {}
    concrete_id_msg = get_message_field(node_message, 3)

    node_type_id_int = get_int_field(generic_id_msg, 5)
    node_type_entry = node_entry_by_id.get(int(node_type_id_int)) if isinstance(node_type_id_int, int) else None
    node_type_name = str(node_type_entry.get("Name") or "").strip() if isinstance(node_type_entry, dict) else ""
    node_type_class = str(node_type_entry.get("Class") or "").strip() if isinstance(node_type_entry, dict) else ""
    node_type_family = str(node_type_entry.get("Family") or "").strip() if isinstance(node_type_entry, dict) else ""
    node_type_inputs = list(node_type_entry.get("Inputs") or []) if isinstance(node_type_entry, dict) else []
    node_type_outputs = list(node_type_entry.get("Outputs") or []) if isinstance(node_type_entry, dict) else []

    pos_x = get_float32_field(node_message, 5) or 0.0
    pos_y = get_float32_field(node_message, 6) or 0.0

    node_comment_msg = get_message_field(node_message, 7)
    node_comment = parse_comment_message(node_comment_msg) if isinstance(node_comment_msg, dict) else None

    node_input_msg = get_message_field(node_message, 8)
    node_input = None
    if isinstance(node_input_msg, dict):
        node_input = {"xxx_int": get_int_field(node_input_msg, 1)}

    using_structs: List[Dict[str, Any]] = []
    for info_msg in iter_message_nodes(get_field(node_message, 10)):
        using_structs.append(parse_graph_affiliation_info_message(info_msg))

    raw_pins = list(iter_message_nodes(get_field(node_message, 4)))
    pins: List[Dict[str, Any]] = []
    for pin_msg in raw_pins:
        pins.append(parse_node_pin(pin_msg, type_entry_by_id=type_entry_by_id))

    edges = parse_edges_from_pins(node_index_int=int(node_index_int), pins=pins)

    return {
        "node_index_int": int(node_index_int),
        "node_type_id_int": int(node_type_id_int) if isinstance(node_type_id_int, int) else None,
        "node_type_name": node_type_name,
        "node_type_class": node_type_class,
        "node_type_family": node_type_family,
        "node_type_inputs": node_type_inputs,
        "node_type_outputs": node_type_outputs,
        "generic_id": parse_node_property(generic_id_msg),
        "concrete_id": parse_node_property(concrete_id_msg) if isinstance(concrete_id_msg, dict) else None,
        "pos": {"x": float(pos_x), "y": float(pos_y)},
        "comment": node_comment,
        "input": node_input,
        "using_structs": using_structs,
        "pin_count": len(pins),
        "pins": pins,
        "edges_from_pins": edges,
    }


def parse_node_graph(
    *,
    node_graph_message: FieldMap,
    node_entry_by_id: Dict[int, Dict[str, Any]],
    type_entry_by_id: Dict[int, Dict[str, Any]],
    graph_unit_message: Optional[FieldMap] = None,
) -> Dict[str, Any]:
    graph_unit_message = graph_unit_message or {}

    graph_unit_id_msg = get_message_field(graph_unit_message, 1) or {}
    graph_unit_id_int = get_int_field(graph_unit_id_msg, 4)
    graph_unit_class_int = get_int_field(graph_unit_id_msg, 2)
    graph_unit_type_int = get_int_field(graph_unit_id_msg, 3)
    graph_unit_which_int = get_int_field(graph_unit_message, 5)
    graph_unit_name = get_utf8_field(graph_unit_message, 3) or ""

    graph_id_msg = get_message_field(node_graph_message, 1) or {}
    graph_id_int = get_int_field(graph_id_msg, 5) or 0
    graph_name = get_utf8_field(node_graph_message, 2) or ""
    graph_scope = infer_graph_scope_from_id_int(graph_id_int)

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    for raw_node_msg in iter_message_nodes(get_field(node_graph_message, 3)):
        parsed_node = parse_graph_node(
            raw_node_msg,
            node_entry_by_id=node_entry_by_id,
            type_entry_by_id=type_entry_by_id,
        )
        nodes.append(parsed_node)
        edges.extend(parsed_node.get("edges_from_pins") or [])

    graph_comments: List[Dict[str, Any]] = []
    for comment_msg in iter_message_nodes(get_field(node_graph_message, 5)):
        graph_comments.append(parse_comment_message(comment_msg))

    graph_variables: List[Dict[str, Any]] = []
    for variable_msg in iter_message_nodes(get_field(node_graph_message, 6)):
        graph_variables.append(parse_graph_variable_message(variable_msg, type_entry_by_id=type_entry_by_id))

    affiliations: List[Dict[str, Any]] = []
    for aff_msg in iter_message_nodes(get_field(node_graph_message, 7)):
        affiliations.append(parse_graph_affiliation_message(aff_msg))

    composite_pins: List[Dict[str, Any]] = []
    for pin_msg in iter_message_nodes(get_field(node_graph_message, 4)):
        composite_pins.append(parse_composite_pin_message(pin_msg))

    # 去重 edges（同一条边可能在多处被重复表达）
    edge_key_seen: set[str] = set()
    dedup_edges: List[Dict[str, Any]] = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        key = (
            f"{edge.get('edge_kind')}:"
            f"{edge.get('src_node_index_int')}:{edge.get('src_port_index_int')}->"
            f"{edge.get('dst_node_index_int')}:{edge.get('dst_port_index_int')}"
        )
        if key in edge_key_seen:
            continue
        edge_key_seen.add(key)
        dedup_edges.append(edge)

    return {
        "schema_version": 2,
        "graph_id_int": int(graph_id_int),
        "graph_name": graph_name,
        "graph_scope": graph_scope,
        "node_count": len(nodes),
        "nodes": nodes,
        "edges": dedup_edges,
        "graph_comments": graph_comments,
        "graph_variables": graph_variables,
        "affiliations": affiliations,
        "composite_pins": composite_pins,
        "graph_meta": {
            "xxx_int": get_int_field(node_graph_message, 100),
            "xxxx_float": get_float32_field(node_graph_message, 101),
        },
        "graph_info": {
            "class_int": get_int_field(graph_id_msg, 1),
            "type_int": get_int_field(graph_id_msg, 2),
            "kind_int": get_int_field(graph_id_msg, 3),
        },
        "graph_unit": {
            "id_int": int(graph_unit_id_int) if isinstance(graph_unit_id_int, int) else None,
            "class_int": int(graph_unit_class_int) if isinstance(graph_unit_class_int, int) else None,
            "type_int": int(graph_unit_type_int) if isinstance(graph_unit_type_int, int) else None,
            "which_int": int(graph_unit_which_int) if isinstance(graph_unit_which_int, int) else None,
            "name": graph_unit_name,
        },
    }


