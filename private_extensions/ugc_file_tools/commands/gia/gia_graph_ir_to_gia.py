from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.gia.container import unwrap_gia_container, validate_gia_container_file, wrap_gia_container
from ugc_file_tools.gia.varbase_semantics import as_list, decoded_field_map_to_numeric_message
from ugc_file_tools.gil_dump_codec.protobuf_like import decode_message_to_field_map, encode_message
from ugc_file_tools.node_graph_semantics.var_base import (
    build_var_base_message_server,
    build_var_base_message_server_empty,
    build_var_base_message_server_for_dict,
)
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir


def _read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _build_index_message(index_ir: Dict[str, Any]) -> Dict[str, Any]:
    msg: Dict[str, Any] = {
        "1": int(index_ir.get("kind_int") or 0),
        "2": int(index_ir.get("index_int") or 0),
    }
    client_exec_id = index_ir.get("client_exec_node_id_int")
    if isinstance(client_exec_id, int):
        msg["100"] = {"1": int(client_exec_id)}
    return msg


def _build_comment_message(comment_ir: Dict[str, Any]) -> Dict[str, Any]:
    msg: Dict[str, Any] = {"1": str(comment_ir.get("content") or "")}
    x = comment_ir.get("x")
    y = comment_ir.get("y")
    if isinstance(x, (int, float)):
        msg["2"] = float(x)
    if isinstance(y, (int, float)):
        msg["3"] = float(y)
    return msg


def _build_node_graph_id_message(id_ir: Dict[str, Any]) -> Dict[str, Any]:
    msg: Dict[str, Any] = {}
    for key, field_number in (("class_int", "1"), ("type_int", "2"), ("kind_int", "3"), ("id_int", "5")):
        value = id_ir.get(key)
        if isinstance(value, int):
            msg[field_number] = int(value)
    return msg


def _build_graph_affiliation_info_message(info_ir: Dict[str, Any]) -> Dict[str, Any]:
    msg: Dict[str, Any] = {}
    source = info_ir.get("source")
    if isinstance(source, dict):
        msg["1"] = _build_node_graph_id_message(source)
    type_xxx = info_ir.get("type_xxx_int")
    if isinstance(type_xxx, int):
        msg["2"] = int(type_xxx)
    always_one = info_ir.get("always_one_xxxx_int")
    if isinstance(always_one, int):
        msg["3"] = int(always_one)
    struct_id = info_ir.get("struct_id_int")
    if isinstance(struct_id, int):
        msg["100"] = {"1": int(struct_id)}
    return msg


def _build_graph_affiliation_message(aff_ir: Dict[str, Any]) -> Dict[str, Any]:
    msg: Dict[str, Any] = {}
    info = aff_ir.get("info")
    if isinstance(info, dict):
        msg["1"] = _build_graph_affiliation_info_message(info)
    type_int = aff_ir.get("type_int")
    if isinstance(type_int, int):
        msg["2"] = {"1": int(type_int)}
    return msg


def _build_node_connection_message(conn_ir: Dict[str, Any]) -> Dict[str, Any]:
    remote_node_index_int = conn_ir.get("remote_node_index_int")
    if not isinstance(remote_node_index_int, int):
        raise ValueError(f"NodeConnection.remote_node_index_int 不能为空：{conn_ir!r}")
    msg: Dict[str, Any] = {"1": int(remote_node_index_int)}

    connect = conn_ir.get("connect")
    if not isinstance(connect, dict):
        raise ValueError(f"NodeConnection.connect 不能为空：{conn_ir!r}")
    msg["2"] = _build_index_message(connect)

    connect2 = conn_ir.get("connect2")
    if isinstance(connect2, dict) and connect2:
        msg["3"] = _build_index_message(connect2)
    return msg


def _build_var_base_for_type(*, var_type_int: int, value: Any, dict_key_type_int: Optional[int], dict_value_type_int: Optional[int]) -> Dict[str, Any]:
    vt = int(var_type_int)
    if vt == 27:
        if not isinstance(dict_key_type_int, int) or not isinstance(dict_value_type_int, int):
            raise ValueError(
                "字典 VarBase 需要 dict_key_type_int/dict_value_type_int（请从解析结果中携带，或手工补齐）："
                f"var_type_int={vt} dict_key_type_int={dict_key_type_int!r} dict_value_type_int={dict_value_type_int!r}"
            )
        return build_var_base_message_server_for_dict(
            dict_key_var_type_int=int(dict_key_type_int),
            dict_value_var_type_int=int(dict_value_type_int),
            default_value=value,
        )

    if value is None:
        return build_var_base_message_server_empty(var_type_int=int(vt))
    return build_var_base_message_server(var_type_int=int(vt), value=value)


def _build_node_pin_message(pin_ir: Dict[str, Any]) -> Dict[str, Any]:
    kind_int = pin_ir.get("kind_int")
    index_int = pin_ir.get("index_int")
    if not isinstance(kind_int, int) or not isinstance(index_int, int):
        raise ValueError(f"NodePin 缺少 kind_int/index_int：{pin_ir!r}")

    var_type_int_raw = pin_ir.get("type_id_int")
    var_type_int = int(var_type_int_raw) if isinstance(var_type_int_raw, int) else 0

    # META pins（信号绑定）：
    # 真源样本中 META pin 通常不写 field_4(type_id)，而是仅在 field_3(VarBase) 中写入字符串；
    # 若错误写入 field_4，编辑器可能直接拒绝导入且不给原因。
    if int(kind_int) == 5 and isinstance(pin_ir.get("value"), str) and str(pin_ir.get("value") or "").strip() != "":
        var_base = _build_var_base_for_type(
            var_type_int=6,
            value=str(pin_ir.get("value") or ""),
            dict_key_type_int=None,
            dict_value_type_int=None,
        )
        i1_msg_meta: Dict[str, Any] = {"1": int(kind_int), "2": int(index_int)}
        msg_meta: Dict[str, Any] = {"1": i1_msg_meta, "3": var_base}
        client_exec_node = pin_ir.get("client_exec_node")
        if isinstance(client_exec_node, dict) and client_exec_node:
            msg_meta["6"] = _build_index_message(client_exec_node)
        composite_pin_index_int = pin_ir.get("composite_pin_index_int")
        if isinstance(composite_pin_index_int, int):
            msg_meta["7"] = int(composite_pin_index_int)
        return msg_meta

    # Flow pins（InFlow/OutFlow）通常不携带类型/常量值；保持最小编码，避免强行构造 VarBase。
    if var_type_int == 0:
        i1_msg: Dict[str, Any] = {"1": int(kind_int), "2": int(index_int)}
        i1_client_exec_id = pin_ir.get("i1_client_exec_node_id_int")
        if isinstance(i1_client_exec_id, int):
            i1_msg["100"] = {"1": int(i1_client_exec_id)}

        msg: Dict[str, Any] = {"1": i1_msg}
        i2 = pin_ir.get("i2")
        if isinstance(i2, dict) and i2:
            msg["2"] = _build_index_message(i2)
        client_exec_node = pin_ir.get("client_exec_node")
        if isinstance(client_exec_node, dict) and client_exec_node:
            msg["6"] = _build_index_message(client_exec_node)
        composite_pin_index_int = pin_ir.get("composite_pin_index_int")
        if isinstance(composite_pin_index_int, int):
            msg["7"] = int(composite_pin_index_int)
        connects_ir = pin_ir.get("connects") or []
        connects: List[Dict[str, Any]] = []
        for connection in as_list(connects_ir):
            if not isinstance(connection, dict):
                continue
            connects.append(_build_node_connection_message(connection))
        if connects:
            msg["5"] = connects
        return msg

    value = pin_ir.get("value")
    dict_key_type_int = pin_ir.get("dict_key_type_int")
    dict_value_type_int = pin_ir.get("dict_value_type_int")
    var_base = _build_var_base_for_type(
        var_type_int=int(var_type_int),
        value=value,
        dict_key_type_int=int(dict_key_type_int) if isinstance(dict_key_type_int, int) else None,
        dict_value_type_int=int(dict_value_type_int) if isinstance(dict_value_type_int, int) else None,
    )

    i1_msg2: Dict[str, Any] = {"1": int(kind_int), "2": int(index_int)}
    i1_client_exec_id2 = pin_ir.get("i1_client_exec_node_id_int")
    if isinstance(i1_client_exec_id2, int):
        i1_msg2["100"] = {"1": int(i1_client_exec_id2)}

    msg: Dict[str, Any] = {
        "1": i1_msg2,
        "3": var_base,
        "4": int(var_type_int),
    }

    i2 = pin_ir.get("i2")
    if isinstance(i2, dict) and i2:
        msg["2"] = _build_index_message(i2)

    client_exec_node2 = pin_ir.get("client_exec_node")
    if isinstance(client_exec_node2, dict) and client_exec_node2:
        msg["6"] = _build_index_message(client_exec_node2)

    composite_pin_index_int2 = pin_ir.get("composite_pin_index_int")
    if isinstance(composite_pin_index_int2, int):
        msg["7"] = int(composite_pin_index_int2)

    connects_ir = pin_ir.get("connects") or []
    connects: List[Dict[str, Any]] = []
    for connection in as_list(connects_ir):
        if not isinstance(connection, dict):
            continue
        connects.append(_build_node_connection_message(connection))
    if connects:
        msg["5"] = connects

    return msg


def _build_node_property_message(prop_ir: Dict[str, Any]) -> Dict[str, Any]:
    msg: Dict[str, Any] = {}
    for key, field_number in (("class_int", "1"), ("type_int", "2"), ("kind_int", "3"), ("node_id_int", "5")):
        value = prop_ir.get(key)
        if isinstance(value, int):
            msg[field_number] = int(value)
    return msg


def _build_graph_node_message(node_ir: Dict[str, Any]) -> Dict[str, Any]:
    node_index_int = node_ir.get("node_index_int")
    if not isinstance(node_index_int, int):
        raise ValueError(f"node_index_int 不能为空：{node_ir!r}")

    generic_id = node_ir.get("generic_id")
    if not isinstance(generic_id, dict):
        raise ValueError(f"generic_id 不能为空：node_index_int={node_index_int} generic_id={generic_id!r}")

    pos = node_ir.get("pos") or {}
    x = pos.get("x")
    y = pos.get("y")
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        raise ValueError(f"pos.x/pos.y 不能为空：node_index_int={node_index_int} pos={pos!r}")

    msg: Dict[str, Any] = {
        "1": int(node_index_int),
        "2": _build_node_property_message(generic_id),
        "5": float(x),
        "6": float(y),
    }

    concrete_id = node_ir.get("concrete_id")
    if isinstance(concrete_id, dict) and concrete_id:
        msg["3"] = _build_node_property_message(concrete_id)

    pins_ir = node_ir.get("pins") or []
    pins: List[Dict[str, Any]] = []
    for pin in as_list(pins_ir):
        if not isinstance(pin, dict):
            continue
        pins.append(_build_node_pin_message(pin))
    if pins:
        msg["4"] = pins

    comment = node_ir.get("comment")
    if isinstance(comment, dict) and (str(comment.get("content") or "").strip() != ""):
        msg["7"] = _build_comment_message(comment)

    node_input = node_ir.get("input")
    if isinstance(node_input, dict):
        xxx_int = node_input.get("xxx_int")
        if isinstance(xxx_int, int):
            msg["8"] = {"1": int(xxx_int)}

    using_structs_ir = node_ir.get("using_structs") or []
    using_structs: List[Dict[str, Any]] = []
    for info in as_list(using_structs_ir):
        if not isinstance(info, dict):
            continue
        using_structs.append(_build_graph_affiliation_info_message(info))
    if using_structs:
        msg["10"] = using_structs

    return msg


def _build_graph_variable_message(var_ir: Dict[str, Any]) -> Dict[str, Any]:
    name = str(var_ir.get("name") or "").strip()
    if name == "":
        raise ValueError(f"GraphVariable.name 不能为空：{var_ir!r}")

    var_type_int = var_ir.get("var_type_int")
    if not isinstance(var_type_int, int):
        raise ValueError(f"GraphVariable.var_type_int 不能为空：name={name!r} var={var_ir!r}")

    key_type_int = var_ir.get("key_type_int")
    value_type_int = var_ir.get("value_type_int")
    if not isinstance(key_type_int, int):
        key_type_int = 6
    if not isinstance(value_type_int, int):
        value_type_int = 6

    default_value = var_ir.get("default_value")
    var_base = _build_var_base_for_type(
        var_type_int=int(var_type_int),
        value=default_value,
        dict_key_type_int=int(key_type_int) if int(var_type_int) == 27 else None,
        dict_value_type_int=int(value_type_int) if int(var_type_int) == 27 else None,
    )

    msg: Dict[str, Any] = {
        "2": name,
        "3": int(var_type_int),
        "4": var_base,
        "7": int(key_type_int),
        "8": int(value_type_int),
    }

    exposed = var_ir.get("exposed")
    if isinstance(exposed, bool):
        msg["5"] = bool(exposed)
    struct_id_int = var_ir.get("struct_id_int")
    if isinstance(struct_id_int, int):
        msg["6"] = int(struct_id_int)

    return msg


def _build_composite_pin_message(pin_ir: Dict[str, Any]) -> Dict[str, Any]:
    outer = pin_ir.get("outer_pin")
    inner = pin_ir.get("inner_pin")
    inner2 = pin_ir.get("inner_pin2")
    if not isinstance(outer, dict) or not isinstance(inner, dict):
        raise ValueError(f"CompositePin.outer_pin/inner_pin 不能为空：{pin_ir!r}")
    msg: Dict[str, Any] = {
        "1": _build_index_message(outer),
        "3": _build_index_message(inner),
    }
    inner_node_id_int = pin_ir.get("inner_node_id_int")
    if isinstance(inner_node_id_int, int):
        msg["2"] = int(inner_node_id_int)
    if isinstance(inner2, dict) and inner2:
        msg["4"] = _build_index_message(inner2)
    return msg


def _build_node_graph_message(graph_ir: Dict[str, Any]) -> Dict[str, Any]:
    graph_id_int = graph_ir.get("graph_id_int")
    if not isinstance(graph_id_int, int):
        raise ValueError(f"graph_id_int 不能为空：{graph_ir.get('graph_id_int')!r}")

    graph_name = str(graph_ir.get("graph_name") or "").strip()
    graph_info = graph_ir.get("graph_info") or {}
    if not isinstance(graph_info, dict):
        graph_info = {}

    id_msg: Dict[str, Any] = {}
    for key, field_number in (("class_int", "1"), ("type_int", "2"), ("kind_int", "3")):
        value = graph_info.get(key)
        if isinstance(value, int):
            id_msg[field_number] = int(value)
    id_msg["5"] = int(graph_id_int)

    msg: Dict[str, Any] = {
        "1": id_msg,
        "2": graph_name,
    }

    nodes_ir = graph_ir.get("nodes") or []
    nodes: List[Dict[str, Any]] = []
    for node in as_list(nodes_ir):
        if not isinstance(node, dict):
            continue
        nodes.append(_build_graph_node_message(node))
    msg["3"] = nodes

    graph_comments_ir = graph_ir.get("graph_comments") or []
    comments: List[Dict[str, Any]] = []
    for comment in as_list(graph_comments_ir):
        if not isinstance(comment, dict):
            continue
        if str(comment.get("content") or "").strip() == "":
            continue
        comments.append(_build_comment_message(comment))
    if comments:
        msg["5"] = comments

    graph_variables_ir = graph_ir.get("graph_variables") or []
    variables: List[Dict[str, Any]] = []
    for var in as_list(graph_variables_ir):
        if not isinstance(var, dict):
            continue
        variables.append(_build_graph_variable_message(var))
    if variables:
        msg["6"] = variables

    affiliations_ir = graph_ir.get("affiliations") or []
    affs: List[Dict[str, Any]] = []
    for aff in as_list(affiliations_ir):
        if not isinstance(aff, dict):
            continue
        affs.append(_build_graph_affiliation_message(aff))
    if affs:
        msg["7"] = affs

    composite_pins_ir = graph_ir.get("composite_pins") or []
    cps: List[Dict[str, Any]] = []
    for cp in as_list(composite_pins_ir):
        if not isinstance(cp, dict):
            continue
        cps.append(_build_composite_pin_message(cp))
    if cps:
        msg["4"] = cps

    graph_meta = graph_ir.get("graph_meta") or {}
    if isinstance(graph_meta, dict):
        xxx_int = graph_meta.get("xxx_int")
        xxxx_float = graph_meta.get("xxxx_float")
        if isinstance(xxx_int, int):
            msg["100"] = int(xxx_int)
        if isinstance(xxxx_float, (int, float)):
            msg["101"] = float(xxxx_float)

    return msg


def _build_graph_unit_message(graph_ir: Dict[str, Any], node_graph_message: Dict[str, Any]) -> Dict[str, Any]:
    graph_unit = graph_ir.get("graph_unit") or {}
    if not isinstance(graph_unit, dict):
        graph_unit = {}

    unit_id_int = graph_unit.get("id_int")
    unit_type_int = graph_unit.get("type_int")
    unit_class_int = graph_unit.get("class_int")
    unit_which_int = graph_unit.get("which_int")
    unit_name = str(graph_unit.get("name") or "").strip()

    if not isinstance(unit_id_int, int):
        unit_id_int = int(graph_ir.get("graph_id_int") or 0)
    if not isinstance(unit_type_int, int):
        unit_type_int = 0
    if not isinstance(unit_class_int, int):
        unit_class_int = 5
    if not isinstance(unit_which_int, int):
        unit_which_int = 0

    # 真源样本中，GraphUnit.id 的 type 字段（field_3）在为 0 时通常省略不写。
    # 部分导入/校验逻辑对“显式写 0”更严格，因此这里对齐样本：仅在非 0 时写入。
    unit_id_msg: Dict[str, Any] = {"2": int(unit_class_int), "4": int(unit_id_int)}
    if int(unit_type_int) != 0:
        unit_id_msg["3"] = int(unit_type_int)

    return {
        "1": unit_id_msg,
        "3": unit_name,
        "5": int(unit_which_int),
        "13": {"1": {"1": node_graph_message}},
    }


def _build_root_message(*, graph_ir: Dict[str, Any]) -> Dict[str, Any]:
    node_graph_message = _build_node_graph_message(graph_ir)
    graph_unit_message = _build_graph_unit_message(graph_ir, node_graph_message)

    file_path = str(graph_ir.get("root_file_path") or "").strip()
    game_version = str(graph_ir.get("root_game_version") or "").strip()
    if file_path == "":
        file_path = "0-0-0-untitled.gia"
    if game_version == "":
        game_version = "6.2.0"

    return {
        "1": graph_unit_message,
        "3": file_path,
        "5": game_version,
    }


def _iter_graph_units_in_root(root_message: Dict[str, Any]) -> List[Tuple[str, int, Dict[str, Any]]]:
    units: List[Tuple[str, int, Dict[str, Any]]] = []
    main = root_message.get("1")
    if isinstance(main, dict):
        units.append(("graph", 0, main))
    for i, unit in enumerate(as_list(root_message.get("2"))):
        if isinstance(unit, dict):
            units.append(("accessory", int(i), unit))
    return units


def _get_node_graph_from_graph_unit(graph_unit_message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    wrapper = graph_unit_message.get("13")
    if not isinstance(wrapper, dict):
        return None
    inner = wrapper.get("1")
    if not isinstance(inner, dict):
        return None
    node_graph = inner.get("1")
    if not isinstance(node_graph, dict):
        return None
    return node_graph


def _get_node_graph_id_int(node_graph_message: Dict[str, Any]) -> Optional[int]:
    id_msg = node_graph_message.get("1")
    if not isinstance(id_msg, dict):
        return None
    value = id_msg.get("5")
    if isinstance(value, int):
        return int(value)
    return None


def patch_gia_with_graph_ir(
    *,
    base_gia_path: Path,
    graph_ir: Dict[str, Any],
    output_gia_path: Path,
    check_header: bool,
    decode_max_depth: int,
) -> Dict[str, Any]:
    base_gia_path = Path(base_gia_path).resolve()
    if check_header:
        validate_gia_container_file(base_gia_path)

    proto_bytes = unwrap_gia_container(base_gia_path, check_header=False)
    root_fields, consumed = decode_message_to_field_map(
        data_bytes=proto_bytes,
        start_offset=0,
        end_offset=len(proto_bytes),
        remaining_depth=int(decode_max_depth),
    )
    if consumed != len(proto_bytes):
        raise ValueError(
            "protobuf 解析未消费完整字节流："
            f"consumed={consumed} total={len(proto_bytes)} file={str(base_gia_path)!r}"
        )

    root_message = decoded_field_map_to_numeric_message(root_fields)

    target_graph_id_int = graph_ir.get("graph_id_int")
    if not isinstance(target_graph_id_int, int):
        raise ValueError(f"graph_ir.graph_id_int 不能为空：{target_graph_id_int!r}")

    new_node_graph = _build_node_graph_message(graph_ir)

    found_ids: List[int] = []
    patched = False
    for _kind, _index, unit in _iter_graph_units_in_root(root_message):
        node_graph = _get_node_graph_from_graph_unit(unit)
        if node_graph is None:
            continue
        gid = _get_node_graph_id_int(node_graph)
        if isinstance(gid, int):
            found_ids.append(int(gid))
        if gid != int(target_graph_id_int):
            continue

        # Patch NodeGraph itself
        node_graph.clear()
        node_graph.update(new_node_graph)

        # Keep unit name in sync (best-effort)
        unit_name = str((graph_ir.get("graph_unit") or {}).get("name") or "").strip()
        if unit_name != "":
            unit["3"] = unit_name

        patched = True
        break

    if not patched:
        raise ValueError(f"未在 base_gia 中找到目标 graph_id={int(target_graph_id_int)}；已发现: {sorted(set(found_ids))}")

    out_bytes = wrap_gia_container(encode_message(root_message))
    output_gia_path = resolve_output_file_path_in_out_dir(Path(output_gia_path))
    output_gia_path.parent.mkdir(parents=True, exist_ok=True)
    output_gia_path.write_bytes(out_bytes)

    return {
        "mode": "patch",
        "base_gia_file": str(base_gia_path),
        "output_gia_file": str(output_gia_path),
        "graph_id_int": int(target_graph_id_int),
    }


def create_gia_from_graph_ir(*, graph_ir: Dict[str, Any], output_gia_path: Path) -> Dict[str, Any]:
    root_message = _build_root_message(graph_ir=graph_ir)
    out_bytes = wrap_gia_container(encode_message(root_message))
    output_gia_path = resolve_output_file_path_in_out_dir(Path(output_gia_path))
    output_gia_path.parent.mkdir(parents=True, exist_ok=True)
    output_gia_path.write_bytes(out_bytes)
    return {
        "mode": "new",
        "output_gia_file": str(output_gia_path),
        "graph_id_int": int(graph_ir.get("graph_id_int") or 0),
    }


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    argument_parser = argparse.ArgumentParser(
        description="将 parse_gia_to_graph_ir 产出的 Graph IR JSON 写回/生成 .gia（纯 Python；无 Node/TS 依赖）。"
    )
    argument_parser.add_argument("--input-ir", dest="input_ir_json", required=True, help="输入 Graph IR JSON（单图）")
    argument_parser.add_argument(
        "--output",
        dest="output_gia_file",
        required=True,
        help="输出 .gia 路径（会强制落盘到 ugc_file_tools/out/）",
    )
    argument_parser.add_argument(
        "--base-gia",
        dest="base_gia_file",
        default="",
        help="可选：提供 base .gia，则按 graph_id 匹配并 patch 该图；不提供则生成新 .gia。",
    )
    argument_parser.add_argument(
        "--check-header",
        dest="check_header",
        action="store_true",
        help="patch 模式下严格校验 base .gia 容器头/尾。",
    )
    argument_parser.add_argument(
        "--decode-max-depth",
        dest="decode_max_depth",
        type=int,
        default=16,
        help="patch 模式下 protobuf 解码深度上限（默认 16）。",
    )

    arguments = argument_parser.parse_args(list(argv) if argv is not None else None)

    graph_ir_raw = _read_json(Path(arguments.input_ir_json).resolve())
    if not isinstance(graph_ir_raw, dict):
        raise ValueError("input_ir_json must be a json object (dict)")

    output_gia_path = Path(arguments.output_gia_file)
    base_gia_text = str(arguments.base_gia_file or "").strip()
    if base_gia_text != "":
        result = patch_gia_with_graph_ir(
            base_gia_path=Path(base_gia_text),
            graph_ir=graph_ir_raw,
            output_gia_path=output_gia_path,
            check_header=bool(arguments.check_header),
            decode_max_depth=int(arguments.decode_max_depth),
        )
    else:
        result = create_gia_from_graph_ir(
            graph_ir=graph_ir_raw,
            output_gia_path=output_gia_path,
        )

    print("=" * 80)
    print("GIA 写回/生成完成：")
    print(f"- mode: {result.get('mode')}")
    if result.get("base_gia_file"):
        print(f"- base_gia_file: {result.get('base_gia_file')}")
    print(f"- output_gia_file: {result.get('output_gia_file')}")
    print(f"- graph_id_int: {result.get('graph_id_int')}")
    print("=" * 80)


if __name__ == "__main__":
    main()




