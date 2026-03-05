from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ugc_file_tools.decode_gil import decode_bytes_to_python

from .json_io import read_json_file


def _decode_base64_utf8_without_padding(base64_text: str) -> str:
    cleaned_text = str(base64_text or "")
    padding = "=" * ((4 - (len(cleaned_text) % 4)) % 4)
    decoded_bytes = base64.b64decode(cleaned_text + padding)
    return decoded_bytes.decode("utf-8", errors="ignore")


def _collect_utf8_values_from_generic_decoded(python_object: Any) -> List[str]:
    results: List[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            utf8_value = value.get("utf8")
            if isinstance(utf8_value, str) and utf8_value.strip() != "":
                results.append(utf8_value)
            for child in value.values():
                walk(child)
            return
        if isinstance(value, list):
            for child in value:
                walk(child)
            return

    walk(python_object)
    # 去重但保留相对稳定顺序
    unique_results: List[str] = []
    seen: set[str] = set()
    for text in results:
        if text in seen:
            continue
        seen.add(text)
        unique_results.append(text)
    return unique_results


@dataclass(frozen=True, slots=True)
class ParsedNodePort:
    port_index_int: int
    port_name: str
    source_path: str
    raw_port_object: Dict[str, Any]


@dataclass(frozen=True, slots=True)
class ParsedNodeDefinition:
    node_def_id_int: int
    node_name: str
    source_pyugc_path: str
    ports_by_index: Dict[int, ParsedNodePort]
    raw_node_def_object: Dict[str, Any]


@dataclass(frozen=True, slots=True)
class ParsedNodePortBinding:
    port_index_int: int
    port_name: str
    utf8_values: List[str]
    raw_record_decoded: Dict[str, Any]


@dataclass(frozen=True, slots=True)
class ParsedNodeGraphNode:
    node_id_int: int
    pos_x: float
    pos_y: float
    node_def_id_int: Optional[int]
    node_def_name: str
    node_palette_id_int: Optional[int]
    port_bindings: List[ParsedNodePortBinding]
    raw_node_object: Dict[str, Any]


@dataclass(frozen=True, slots=True)
class ParsedDataPortRef:
    port_index_int: int


@dataclass(frozen=True, slots=True)
class ParsedFlowPortRef:
    group_int: int
    branch_int: int


@dataclass(frozen=True, slots=True)
class ParsedNodeGraphEdge:
    edge_kind: str  # "flow" | "data"
    src_node_id_int: int
    dst_node_id_int: int
    src_port: ParsedDataPortRef | ParsedFlowPortRef
    dst_port: ParsedDataPortRef | ParsedFlowPortRef
    record_index: int
    raw_record_decoded: Dict[str, Any]


@dataclass(frozen=True, slots=True)
class ParsedNodeGraph:
    graph_id_int: int
    graph_name: str
    source_pyugc_path: str
    nodes: List[ParsedNodeGraphNode]
    edges: List[ParsedNodeGraphEdge]
    raw_graph_object: Dict[str, Any]


def _iter_dict_nodes_with_path(
    python_object: Any,
    path_parts: Optional[List[str]] = None,
) -> Iterable[Tuple[List[str], Dict[str, Any]]]:
    current_path_parts = path_parts if path_parts is not None else []
    if isinstance(python_object, dict):
        yield current_path_parts, python_object
        for key, child in python_object.items():
            yield from _iter_dict_nodes_with_path(child, current_path_parts + [str(key)])
        return
    if isinstance(python_object, list):
        for index, child in enumerate(python_object):
            yield from _iter_dict_nodes_with_path(child, current_path_parts + [f"[{index}]"])
        return


def _extract_node_ports_from_node_def_object(raw_node_def_object: Dict[str, Any]) -> Dict[int, ParsedNodePort]:
    ports_by_index: Dict[int, ParsedNodePort] = {}

    def add_port(
        *,
        port_index_int: int,
        port_name: str,
        source_path_text: str,
        raw_port_object: Dict[str, Any],
    ) -> None:
        parsed_port = ParsedNodePort(
            port_index_int=int(port_index_int),
            port_name=str(port_name or ""),
            source_path=str(source_path_text or ""),
            raw_port_object=raw_port_object,
        )
        existing = ports_by_index.get(int(port_index_int))
        if existing is None:
            ports_by_index[int(port_index_int)] = parsed_port
            return
        if existing.port_name == "" and parsed_port.port_name != "":
            ports_by_index[int(port_index_int)] = parsed_port

    def try_extract_port_from_base64_descriptor(base64_text: str) -> Optional[Tuple[int, str, Dict[str, Any]]]:
        cleaned_text = str(base64_text or "").strip()
        if cleaned_text == "":
            return None
        padding = "=" * ((4 - (len(cleaned_text) % 4)) % 4)
        decoded_bytes = base64.b64decode(cleaned_text + padding)
        decoded_object = decode_bytes_to_python(decoded_bytes)
        if not isinstance(decoded_object, dict):
            return None
        field_8 = decoded_object.get("field_8")
        if not isinstance(field_8, dict) or not isinstance(field_8.get("int"), int):
            return None
        port_index_int = int(field_8.get("int"))

        port_name = ""
        field_1 = decoded_object.get("field_1")
        if isinstance(field_1, dict) and isinstance(field_1.get("utf8"), str):
            port_name = field_1.get("utf8").strip()
        if port_name == "":
            return None
        return port_index_int, port_name, {"base64": cleaned_text, "decoded": decoded_object}

    for path_parts, dictionary_value in _iter_dict_nodes_with_path(raw_node_def_object):
        port_index_value = dictionary_value.get("8@int")
        if not isinstance(port_index_value, int):
            continue
        port_index_int = int(port_index_value)

        port_name = ""
        port_name_string = dictionary_value.get("1@string")
        if isinstance(port_name_string, str) and port_name_string.strip() != "":
            port_name = port_name_string.strip()

        port_name_data = dictionary_value.get("1@data")
        if port_name == "" and isinstance(port_name_data, str) and port_name_data.strip() != "":
            decoded_text = _decode_base64_utf8_without_padding(port_name_data.strip())
            if decoded_text.strip() != "":
                port_name = decoded_text.strip()

        source_path_text = "/".join(path_parts)
        add_port(
            port_index_int=port_index_int,
            port_name=port_name,
            source_path_text=source_path_text,
            raw_port_object=dictionary_value,
        )

    # 额外解析：节点定义中常见的“端口描述 base64”（例如 102@data / 102 列表）
    descriptor_text = raw_node_def_object.get("102@data")
    if isinstance(descriptor_text, str) and descriptor_text.strip() != "":
        extracted = try_extract_port_from_base64_descriptor(descriptor_text)
        if extracted is not None:
            port_index_int, port_name, raw_descriptor_object = extracted
            add_port(
                port_index_int=port_index_int,
                port_name=port_name,
                source_path_text="102@data",
                raw_port_object=raw_descriptor_object,
            )

    descriptor_list = raw_node_def_object.get("102")
    if isinstance(descriptor_list, list):
        stack: List[Any] = list(descriptor_list)
        while stack:
            current = stack.pop(0)
            if isinstance(current, str):
                extracted = try_extract_port_from_base64_descriptor(current)
                if extracted is None:
                    continue
                port_index_int, port_name, raw_descriptor_object = extracted
                add_port(
                    port_index_int=port_index_int,
                    port_name=port_name,
                    source_path_text="102",
                    raw_port_object=raw_descriptor_object,
                )
                continue
            if isinstance(current, list):
                stack.extend(current)

    return ports_by_index


def load_pyugc_node_definitions_for_package(package_root: Path) -> Dict[int, ParsedNodeDefinition]:
    raw_directory = package_root / "节点图" / "原始解析"
    index_file_path = raw_directory / "pyugc_node_defs_index.json"
    index_object = read_json_file(index_file_path)
    if not isinstance(index_object, list):
        raise TypeError("pyugc_node_defs_index.json 格式错误：期望为 list[dict]")

    node_definitions: Dict[int, ParsedNodeDefinition] = {}

    for index_entry in index_object:
        if not isinstance(index_entry, dict):
            continue
        node_def_id_value = index_entry.get("node_def_id_int")
        output_value = index_entry.get("output")
        node_name_value = index_entry.get("node_name")
        source_path_value = index_entry.get("source_pyugc_path")

        if not isinstance(node_def_id_value, int):
            continue
        if not isinstance(output_value, str) or output_value.strip() == "":
            continue

        node_def_id_int = int(node_def_id_value)
        output_path = package_root / Path(output_value)
        payload_object = read_json_file(output_path)
        if not isinstance(payload_object, dict):
            raise TypeError(f"节点定义文件格式错误：{str(output_path)!r}")
        raw_node_def_object = payload_object.get("raw_node_def_object")
        if not isinstance(raw_node_def_object, dict):
            raise TypeError(f"节点定义缺少 raw_node_def_object：{str(output_path)!r}")

        node_name = str(node_name_value or payload_object.get("node_name") or "").strip()
        source_pyugc_path = str(source_path_value or payload_object.get("source_pyugc_path") or "").strip()

        ports_by_index = _extract_node_ports_from_node_def_object(raw_node_def_object)

        node_definitions[node_def_id_int] = ParsedNodeDefinition(
            node_def_id_int=node_def_id_int,
            node_name=node_name,
            source_pyugc_path=source_pyugc_path,
            ports_by_index=ports_by_index,
            raw_node_def_object=raw_node_def_object,
        )

    return node_definitions


def load_pyugc_node_graphs_for_package(
    package_root: Path,
    *,
    node_definitions: Optional[Dict[int, ParsedNodeDefinition]] = None,
) -> Dict[int, ParsedNodeGraph]:
    raw_directory = package_root / "节点图" / "原始解析"
    graphs_index_path = raw_directory / "pyugc_graphs_index.json"
    graphs_index_object = read_json_file(graphs_index_path)
    if not isinstance(graphs_index_object, list):
        raise TypeError("pyugc_graphs_index.json 格式错误：期望为 list[dict]")

    node_definitions_map = node_definitions if node_definitions is not None else {}

    parsed_graphs: Dict[int, ParsedNodeGraph] = {}

    for index_entry in graphs_index_object:
        if not isinstance(index_entry, dict):
            continue
        graph_id_value = index_entry.get("graph_id_int")
        graph_name_value = index_entry.get("graph_name")
        output_value = index_entry.get("output")
        source_path_value = index_entry.get("source_pyugc_path")

        if not isinstance(graph_id_value, int):
            continue
        if not isinstance(output_value, str) or output_value.strip() == "":
            continue

        graph_id_int = int(graph_id_value)
        graph_name = str(graph_name_value or "").strip()
        source_pyugc_path = str(source_path_value or "").strip()

        graph_file_path = package_root / Path(output_value)
        graph_payload = read_json_file(graph_file_path)
        if not isinstance(graph_payload, dict):
            raise TypeError(f"节点图文件格式错误：{str(graph_file_path)!r}")

        raw_graph_object = graph_payload.get("raw_graph_object")
        if not isinstance(raw_graph_object, dict):
            raise TypeError(f"节点图缺少 raw_graph_object：{str(graph_file_path)!r}")

        decoded_nodes = graph_payload.get("decoded_nodes")
        if not isinstance(decoded_nodes, list):
            raise TypeError(f"节点图 decoded_nodes 格式错误：{str(graph_file_path)!r}")

        node_id_set: set[int] = set()
        for node_payload in decoded_nodes:
            if isinstance(node_payload, dict) and isinstance(node_payload.get("node_id_int"), int):
                node_id_set.add(int(node_payload.get("node_id_int")))

        parsed_nodes: List[ParsedNodeGraphNode] = []
        parsed_edges: List[ParsedNodeGraphEdge] = []

        def _get_nested_int(decoded_record: Dict[str, Any], path: List[str]) -> Optional[int]:
            cursor: Any = decoded_record
            for key in path:
                if not isinstance(cursor, dict):
                    return None
                cursor = cursor.get(key)
            if not isinstance(cursor, dict):
                return None
            number = cursor.get("int")
            if isinstance(number, int):
                return int(number)
            return None

        def _parse_edge_from_record(
            decoded_record: Dict[str, Any],
            *,
            current_node_id_int: int,
            record_index: int,
        ) -> Optional[ParsedNodeGraphEdge]:
            """
            解析 record 为 edges（已在 test4 校准图中验证）。

            - 数据边（data）：
              - record 存在 field_4.int（目标节点本地端口索引）
              - field_5.message.field_1.int 指向源节点 node_id
              - field_5.message.field_2.message.field_1/int 为源端口索引（输出端口）
            - 流程边（flow）：
              - record 不存在 field_4
              - record 存放在源节点上
              - field_5.message.field_1.int 指向目标节点 node_id
              - field_1.message.field_1/int + field_1.message.field_2/int 编码源端口（用于区分双分支等多出口）
              - field_5.message.field_2.message.field_1/int 编码目标端口（通常为流程入）
            """
            other_node_id_int = _get_nested_int(decoded_record, ["field_5", "message", "field_1"])
            if not isinstance(other_node_id_int, int):
                return None
            if other_node_id_int not in node_id_set:
                return None

            local_data_port_index_int = _get_nested_int(decoded_record, ["field_4"])
            remote_port_index_a = _get_nested_int(
                decoded_record,
                ["field_5", "message", "field_2", "message", "field_1"],
            )
            remote_port_index_b = _get_nested_int(
                decoded_record,
                ["field_5", "message", "field_3", "message", "field_1"],
            )

            # data: record 在 dst 节点上，field_4 为 dst 端口
            if isinstance(local_data_port_index_int, int):
                src_port_index_int = (
                    remote_port_index_a if isinstance(remote_port_index_a, int) else remote_port_index_b
                )
                if not isinstance(src_port_index_int, int):
                    return None
                return ParsedNodeGraphEdge(
                    edge_kind="data",
                    src_node_id_int=int(other_node_id_int),
                    dst_node_id_int=int(current_node_id_int),
                    src_port=ParsedDataPortRef(port_index_int=int(src_port_index_int)),
                    dst_port=ParsedDataPortRef(port_index_int=int(local_data_port_index_int)),
                    record_index=int(record_index),
                    raw_record_decoded=decoded_record,
                )

            # flow: record 在 src 节点上
            src_flow_group_int = _get_nested_int(decoded_record, ["field_1", "message", "field_1"])
            src_flow_branch_int = _get_nested_int(decoded_record, ["field_1", "message", "field_2"])
            dst_flow_group_int = (
                remote_port_index_a if isinstance(remote_port_index_a, int) else remote_port_index_b
            )
            dst_flow_branch_int = _get_nested_int(decoded_record, ["field_5", "message", "field_2", "message", "field_2"])
            if not isinstance(src_flow_group_int, int):
                return None
            if not isinstance(dst_flow_group_int, int):
                return None

            return ParsedNodeGraphEdge(
                edge_kind="flow",
                src_node_id_int=int(current_node_id_int),
                dst_node_id_int=int(other_node_id_int),
                src_port=ParsedFlowPortRef(
                    group_int=int(src_flow_group_int),
                    branch_int=int(src_flow_branch_int) if isinstance(src_flow_branch_int, int) else 0,
                ),
                dst_port=ParsedFlowPortRef(
                    group_int=int(dst_flow_group_int),
                    branch_int=int(dst_flow_branch_int) if isinstance(dst_flow_branch_int, int) else 0,
                ),
                record_index=int(record_index),
                raw_record_decoded=decoded_record,
            )

        for node_payload in decoded_nodes:
            if not isinstance(node_payload, dict):
                continue
            node_id_value = node_payload.get("node_id_int")
            if not isinstance(node_id_value, int):
                continue
            node_id_int = int(node_id_value)

            pos_object = node_payload.get("pos")
            pos_x = 0.0
            pos_y = 0.0
            if isinstance(pos_object, dict):
                pos_x = float(pos_object.get("x", 0.0) or 0.0)
                pos_y = float(pos_object.get("y", 0.0) or 0.0)

            node_def_id_int: Optional[int] = None
            data_2 = node_payload.get("data_2")
            if isinstance(data_2, dict):
                decoded_2 = data_2.get("decoded")
                if isinstance(decoded_2, dict):
                    field_5 = decoded_2.get("field_5")
                    if isinstance(field_5, dict) and isinstance(field_5.get("int"), int):
                        node_def_id_int = int(field_5.get("int"))

            node_palette_id_int: Optional[int] = None
            data_3 = node_payload.get("data_3")
            if isinstance(data_3, dict):
                decoded_3 = data_3.get("decoded")
                if isinstance(decoded_3, dict):
                    field_5 = decoded_3.get("field_5")
                    if isinstance(field_5, dict) and isinstance(field_5.get("int"), int):
                        node_palette_id_int = int(field_5.get("int"))

            node_def_name = ""
            ports_by_index: Dict[int, ParsedNodePort] = {}
            if isinstance(node_def_id_int, int):
                matched_node_def = node_definitions_map.get(node_def_id_int)
                if matched_node_def is not None:
                    node_def_name = matched_node_def.node_name
                    ports_by_index = matched_node_def.ports_by_index

            port_bindings: List[ParsedNodePortBinding] = []
            records = node_payload.get("records")
            if isinstance(records, list):
                for record_index, record in enumerate(records):
                    if not isinstance(record, dict):
                        continue
                    decoded_record = record.get("decoded")
                    if not isinstance(decoded_record, dict):
                        continue

                    edge = _parse_edge_from_record(
                        decoded_record,
                        current_node_id_int=node_id_int,
                        record_index=int(record_index),
                    )
                    if edge is not None:
                        parsed_edges.append(edge)

                    field_7 = decoded_record.get("field_7")
                    if not isinstance(field_7, dict) or not isinstance(field_7.get("int"), int):
                        continue

                    port_index_int = int(field_7.get("int"))
                    port_name = ""
                    matched_port = ports_by_index.get(port_index_int)
                    if matched_port is not None and matched_port.port_name.strip() != "":
                        port_name = matched_port.port_name.strip()

                    utf8_values = _collect_utf8_values_from_generic_decoded(decoded_record)
                    port_bindings.append(
                        ParsedNodePortBinding(
                            port_index_int=port_index_int,
                            port_name=port_name,
                            utf8_values=utf8_values,
                            raw_record_decoded=decoded_record,
                        )
                    )

            raw_node_object = node_payload.get("raw_node_object")
            if not isinstance(raw_node_object, dict):
                raw_node_object = {}

            parsed_nodes.append(
                ParsedNodeGraphNode(
                    node_id_int=node_id_int,
                    pos_x=pos_x,
                    pos_y=pos_y,
                    node_def_id_int=node_def_id_int,
                    node_def_name=node_def_name,
                    node_palette_id_int=node_palette_id_int,
                    port_bindings=port_bindings,
                    raw_node_object=raw_node_object,
                )
            )

        parsed_graphs[graph_id_int] = ParsedNodeGraph(
            graph_id_int=graph_id_int,
            graph_name=graph_name,
            source_pyugc_path=source_pyugc_path,
            nodes=parsed_nodes,
            edges=parsed_edges,
            raw_graph_object=raw_graph_object,
        )

    return parsed_graphs


