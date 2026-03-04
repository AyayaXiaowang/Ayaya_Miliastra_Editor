from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.fs_naming import sanitize_file_stem
from ugc_file_tools.graph.pyugc_graph_model_builder import load_node_type_semantic_map
from ugc_file_tools.repo_paths import resolve_graph_generater_root, ugc_file_tools_root


@dataclass(frozen=True, slots=True)
class ResolvedNodeDef:
    node_key: str
    node_def: Any


def _map_node_data_type_expr_to_type_name(type_expr: str) -> str:
    """
    将 node_data TypeEntry.Expression（例如 Int/Bol/L<Int>/D<?,?>/S<?>/E<1028>）映射为引擎“规范中文类型名”。

    说明：
    - GraphVariableConfig.variable_type 的唯一口径为 `engine.type_registry` 的中文类型名；
    - 这里不做“猜测式”容错：无法识别时直接返回空字符串，由上层 fail-fast 抛错。
    """
    from engine.type_registry import (
        TYPE_BOOLEAN,
        TYPE_CAMP,
        TYPE_COMPONENT_ID,
        TYPE_CONFIG_ID,
        TYPE_DICT,
        TYPE_ENTITY,
        TYPE_ENUM,
        TYPE_FLOAT,
        TYPE_GUID,
        TYPE_INTEGER,
        TYPE_STRING,
        TYPE_STRUCT,
        TYPE_SUFFIX_LIST,
        TYPE_VECTOR3,
    )

    text = str(type_expr or "").strip()
    if text == "":
        return ""

    if text.startswith("L<") and text.endswith(">") and len(text) > 3:
        inner = text[2:-1].strip()
        inner_name = _map_node_data_type_expr_to_type_name(inner)
        if inner_name == "":
            return ""
        # 统一用后缀“列表”（对齐 type_registry 口径）
        if inner_name.endswith(TYPE_SUFFIX_LIST):
            return inner_name
        return f"{inner_name}{TYPE_SUFFIX_LIST}"

    if text.startswith("D<") and text.endswith(">") and len(text) > 3:
        # node_data 的 Dictionary 类型表达式通常为 D<?,?>；具体 KV 类型在 Graph IR 的 key/value 字段里。
        return TYPE_DICT

    if text.startswith("S<") and text.endswith(">") and len(text) > 3:
        # node_data 的 Struct 类型表达式通常为 S<?>；具体 struct 绑定见 Graph IR 的 struct_id_int。
        return TYPE_STRUCT

    if text.startswith("E<") and text.endswith(">") and len(text) > 3:
        # 枚举：E<?> / E<1028> 等
        return TYPE_ENUM

    base = {
        "Ety": TYPE_ENTITY,
        "Gid": TYPE_GUID,
        "Int": TYPE_INTEGER,
        "Bol": TYPE_BOOLEAN,
        "Flt": TYPE_FLOAT,
        "Str": TYPE_STRING,
        "Vec": TYPE_VECTOR3,
        "Cfg": TYPE_CONFIG_ID,
        "Pfb": TYPE_COMPONENT_ID,
        "Fct": TYPE_CAMP,
        "E<?>": TYPE_ENUM,
        "S<?>": TYPE_STRUCT,
        "D<?,?>": TYPE_DICT,
    }.get(text)
    return str(base or "")


def _is_flow_port_name(port_name: str) -> bool:
    from engine.utils.graph.graph_utils import is_flow_port_name as _is_flow

    return bool(_is_flow(str(port_name or "")))


def _iter_flow_inputs(node_def: Any) -> List[str]:
    return [str(p) for p in list(getattr(node_def, "inputs", []) or []) if _is_flow_port_name(str(p))]


def _iter_flow_outputs(node_def: Any) -> List[str]:
    return [str(p) for p in list(getattr(node_def, "outputs", []) or []) if _is_flow_port_name(str(p))]


def _iter_data_inputs(node_def: Any) -> List[str]:
    return [str(p) for p in list(getattr(node_def, "inputs", []) or []) if not _is_flow_port_name(str(p))]


def _iter_data_outputs(node_def: Any) -> List[str]:
    return [str(p) for p in list(getattr(node_def, "outputs", []) or []) if not _is_flow_port_name(str(p))]


def _has_range_ports(ports: List[str]) -> bool:
    return any("~" in str(p) for p in list(ports or []))


def _resolve_node_def_by_name(
    node_name: str,
    *,
    node_library: Dict[str, Any],
    node_name_index: Dict[str, str],
) -> ResolvedNodeDef:
    name_text = str(node_name or "").strip()
    if name_text == "":
        raise ValueError("node_name is empty")
    node_key = node_name_index.get(name_text)
    if not isinstance(node_key, str) or node_key.strip() == "":
        raise KeyError(f"node name not found in node_name_index: {name_text!r}")
    node_def = node_library.get(node_key)
    if node_def is None:
        raise KeyError(f"node key not found in node_library: {node_key!r}")
    return ResolvedNodeDef(node_key=str(node_key), node_def=node_def)


def _normalize_enum_constant(*, node_def: Any, port_name: str, value: Any) -> Any:
    expected_type = str(node_def.get_port_type(str(port_name), is_input=True) or "").strip()
    if expected_type != "枚举":
        return value
    enum_options = getattr(node_def, "input_enum_options", {}) or {}
    candidates = enum_options.get(str(port_name))
    if not (isinstance(candidates, list) and candidates):
        return value
    if isinstance(value, int):
        index0 = int(value)
        index1 = int(value) - 1
        if 0 <= index0 < len(candidates):
            return str(candidates[index0])
        if 0 <= index1 < len(candidates):
            return str(candidates[index1])
        raise IndexError(
            f"enum value out of range: port={port_name!r} value={value} options={candidates!r}"
        )
    return value


def _map_flow_input_index(*, node_title: str, node_def: Any, index_int: int) -> str:
    ports = _iter_flow_inputs(node_def)
    if int(index_int) < 0 or int(index_int) >= len(ports):
        raise IndexError(f"flow input index out of range: node={node_title!r} index={index_int} ports={ports!r}")
    return str(ports[int(index_int)])


def _map_flow_output_index(*, node_title: str, node_def: Any, index_int: int) -> str:
    ports = _iter_flow_outputs(node_def)
    if int(index_int) < 0 or int(index_int) >= len(ports):
        raise IndexError(f"flow output index out of range: node={node_title!r} index={index_int} ports={ports!r}")
    return str(ports[int(index_int)])


def _map_data_input_index(
    *,
    node_title: str,
    node_def: Any,
    index_int: int,
    graph_ir_node: Dict[str, Any],
) -> str:
    title = str(node_title or "").strip()
    if title == "":
        raise ValueError("node_title is empty")

    # 重要：对齐真源 NodeGraph pins 语义（样本校准图已验证）
    # - Assembly_List：index=0 是“元素数量”，实际元素从 index=1 开始，对应端口 "0","1","2"...（即 index-1）
    if title == "拼装列表":
        if int(index_int) <= 0:
            raise ValueError(f"拼装列表 InParam index 必须 >=1（index=0 为长度），got {index_int}")
        return str(int(index_int) - 1)

    # 拼装字典：真源通常包含 count + key/value 交错排列；此处按 index-1 做 (键/值) 交错映射
    if title == "拼装字典":
        if int(index_int) <= 0:
            raise ValueError(f"拼装字典 InParam index 必须 >=1（index=0 预留/计数），got {index_int}")
        zero_based = int(index_int) - 1
        pair_index = int(zero_based // 2)
        in_pair = int(zero_based % 2)
        return f"键{pair_index}" if in_pair == 0 else f"值{pair_index}"

    data_ports = _iter_data_inputs(node_def)
    if int(index_int) < 0 or int(index_int) >= len(data_ports):
        raise IndexError(
            f"data input index out of range: node={title!r} index={index_int} data_ports={data_ports!r} "
            f"(raw_node_type_id={graph_ir_node.get('node_type_id_int')})"
        )
    return str(data_ports[int(index_int)])


def _map_data_output_index(*, node_title: str, node_def: Any, index_int: int) -> str:
    title = str(node_title or "").strip()
    if title == "":
        raise ValueError("node_title is empty")
    data_ports = _iter_data_outputs(node_def)
    if int(index_int) < 0 or int(index_int) >= len(data_ports):
        raise IndexError(f"data output index out of range: node={title!r} index={index_int} data_ports={data_ports!r}")
    return str(data_ports[int(index_int)])


def _extract_list_count_from_pins(pins: List[Dict[str, Any]]) -> int:
    for p in pins or []:
        if not isinstance(p, dict):
            continue
        if int(p.get("kind_int") or 0) != 3:
            continue
        if int(p.get("index_int") or 0) != 0:
            continue
        v = p.get("value")
        if not isinstance(v, int):
            raise TypeError(f"拼装列表长度 pin.value 必须为 int，got: {type(v).__name__}")
        return int(v)
    raise ValueError("拼装列表缺少长度 pin（InParam index=0）")


def build_graph_model_from_graph_ir(
    *,
    package_root: Path,
    graph_ir: Dict[str, Any],
    mapping_path: Path | None = None,
) -> Tuple[Any, Dict[str, Any]]:
    """
    将 `.gia` NodeGraph Graph IR（schema_version=2）转换为 Graph_Generater GraphModel。

    目标：
    - 用于 `.gia 节点图 → 项目存档 Graph Code` 导入链路；
    - 端口 index 语义对齐 NodeGraph pins（flow/data 分离；拼装列表/拼装字典特例）。
    """
    package_root = Path(package_root).resolve()
    if not package_root.is_dir():
        raise FileNotFoundError(f"package_root not found: {str(package_root)!r}")

    graph_scope = str(graph_ir.get("graph_scope") or "").strip().lower()
    if graph_scope not in {"server", "client"}:
        raise ValueError(f"unsupported graph_scope: {graph_scope!r}")

    graph_id_int = graph_ir.get("graph_id_int")
    if not isinstance(graph_id_int, int):
        raise TypeError("graph_ir.graph_id_int must be int")
    graph_name = str(graph_ir.get("graph_name") or "").strip()

    if mapping_path is None:
        mapping_path = (ugc_file_tools_root() / "graph_ir" / "node_type_semantic_map.json").resolve()
    mapping = load_node_type_semantic_map(Path(mapping_path))

    graph_generater_root = resolve_graph_generater_root(package_root)
    graph_root_text = str(graph_generater_root.resolve())
    if graph_root_text not in sys.path:
        sys.path.insert(0, graph_root_text)

    from engine.configs.settings import settings
    from engine.graph.common import node_name_index_from_library
    from engine.graph.models import GraphModel, NodeModel, PortModel
    from engine.nodes.node_registry import get_node_registry

    settings.set_config_path(graph_generater_root.resolve())

    registry = get_node_registry(graph_generater_root.resolve(), include_composite=True)
    node_library = registry.get_library()
    node_name_index = node_name_index_from_library(node_library, scope=graph_scope)

    graph_model = GraphModel()
    graph_model.graph_name = graph_name
    graph_model.graph_id = f"{graph_scope}_graph_{int(graph_id_int)}__{package_root.name}"

    resolved_by_node_index: Dict[int, ResolvedNodeDef] = {}
    node_model_by_node_index: Dict[int, Any] = {}

    nodes = graph_ir.get("nodes")
    if not isinstance(nodes, list):
        raise TypeError("graph_ir.nodes must be list")

    missing_type_ids: Dict[int, List[int]] = {}

    for node_item in nodes:
        if not isinstance(node_item, dict):
            continue
        node_index_int = node_item.get("node_index_int")
        if not isinstance(node_index_int, int):
            continue
        node_type_id_int = node_item.get("node_type_id_int")
        if not isinstance(node_type_id_int, int):
            raise ValueError(f"node missing node_type_id_int: node_index_int={node_index_int}")

        mapped = mapping.get(int(node_type_id_int)) or {}
        node_name_cn = str(mapped.get("graph_generater_node_name") or "").strip()
        if node_name_cn == "":
            missing_type_ids.setdefault(int(node_type_id_int), []).append(int(node_index_int))
            node_name_cn = f"未识别节点类型_{int(node_type_id_int)}"

        if node_name_cn.startswith("未识别节点类型_"):
            # fail-fast：导入场景不生成占位图，避免 silently 写入错误逻辑
            continue

        pos_obj = node_item.get("pos")
        pos_x = 0.0
        pos_y = 0.0
        if isinstance(pos_obj, dict):
            pos_x = float(pos_obj.get("x", 0.0) or 0.0)
            pos_y = float(pos_obj.get("y", 0.0) or 0.0)

        resolved = _resolve_node_def_by_name(
            node_name_cn,
            node_library=node_library,
            node_name_index=node_name_index,
        )
        resolved_by_node_index[int(node_index_int)] = resolved

        node_model = NodeModel(
            id=f"node_{int(node_index_int)}",
            title=str(node_name_cn),
            category=str(getattr(resolved.node_def, "category", "") or ""),
            pos=(pos_x, pos_y),
        )

        inputs = [str(p) for p in list(getattr(resolved.node_def, "inputs", []) or [])]
        outputs = [str(p) for p in list(getattr(resolved.node_def, "outputs", []) or [])]

        if _has_range_ports(inputs) and node_model.title in {"拼装列表", "拼装字典"}:
            node_model.inputs = []
        else:
            node_model.inputs = [PortModel(name=str(p), is_input=True) for p in inputs]
        node_model.outputs = [PortModel(name=str(p), is_input=False) for p in outputs]
        node_model._rebuild_port_maps()

        node_model_by_node_index[int(node_index_int)] = node_model
        graph_model.nodes[node_model.id] = node_model

    if missing_type_ids:
        missing_lines = []
        for tid, node_indices in sorted(missing_type_ids.items(), key=lambda kv: kv[0]):
            missing_lines.append(f"- type_id={tid}: nodes={sorted(node_indices)}")
        raise KeyError(
            "node_type_semantic_map 缺少节点类型映射（无法导入 .gia 节点图）：\n"
            + "\n".join(missing_lines)
            + f"\n(mapping_file={str(Path(mapping_path).resolve())!r})"
        )

    # edges
    edges = graph_ir.get("edges")
    if not isinstance(edges, list):
        raise TypeError("graph_ir.edges must be list")

    def ensure_input_port(node_model: Any, port_name: str) -> None:
        if node_model.get_input_port(port_name) is not None:
            return
        node_model.add_input_port(str(port_name))

    for edge in edges:
        if not isinstance(edge, dict):
            continue
        kind = str(edge.get("edge_kind") or "").strip()
        src_node_index_int = edge.get("src_node_index_int")
        dst_node_index_int = edge.get("dst_node_index_int")
        src_port_index_int = edge.get("src_port_index_int")
        dst_port_index_int = edge.get("dst_port_index_int")
        if not all(isinstance(x, int) for x in (src_node_index_int, dst_node_index_int, src_port_index_int, dst_port_index_int)):
            continue

        src_node_model = node_model_by_node_index.get(int(src_node_index_int))
        dst_node_model = node_model_by_node_index.get(int(dst_node_index_int))
        if src_node_model is None or dst_node_model is None:
            raise KeyError(f"edge references missing node: {edge!r}")

        src_resolved = resolved_by_node_index.get(int(src_node_index_int))
        dst_resolved = resolved_by_node_index.get(int(dst_node_index_int))
        if src_resolved is None or dst_resolved is None:
            raise KeyError(f"edge references missing node def: {edge!r}")

        if kind == "flow":
            src_port_name = _map_flow_output_index(
                node_title=str(src_node_model.title),
                node_def=src_resolved.node_def,
                index_int=int(src_port_index_int),
            )
            dst_port_name = _map_flow_input_index(
                node_title=str(dst_node_model.title),
                node_def=dst_resolved.node_def,
                index_int=int(dst_port_index_int),
            )
        elif kind == "data":
            src_port_name = _map_data_output_index(
                node_title=str(src_node_model.title),
                node_def=src_resolved.node_def,
                index_int=int(src_port_index_int),
            )
            dst_port_name = _map_data_input_index(
                node_title=str(dst_node_model.title),
                node_def=dst_resolved.node_def,
                index_int=int(dst_port_index_int),
                graph_ir_node=next((n for n in nodes if isinstance(n, dict) and int(n.get("node_index_int", -1)) == int(dst_node_index_int)), {}),
            )
            # 变参输入：动态补齐实际端口实例名（如 "0","键0","值0"）
            ensure_input_port(dst_node_model, dst_port_name)
        else:
            raise ValueError(f"unknown edge_kind: {kind!r}")

        graph_model.add_edge(
            str(src_node_model.id),
            str(src_port_name),
            str(dst_node_model.id),
            str(dst_port_name),
        )

    # input constants（仅处理未连线的 InParam pins）
    node_item_by_index: Dict[int, Dict[str, Any]] = {
        int(n.get("node_index_int")): n for n in nodes if isinstance(n, dict) and isinstance(n.get("node_index_int"), int)
    }

    for node_index_int, node_model in node_model_by_node_index.items():
        node_item = node_item_by_index.get(int(node_index_int)) or {}
        pins = node_item.get("pins") or []
        if not isinstance(pins, list):
            continue
        resolved = resolved_by_node_index.get(int(node_index_int))
        if resolved is None:
            continue

        title = str(getattr(node_model, "title", "") or "")
        list_count: Optional[int] = None
        if title == "拼装列表":
            list_count = _extract_list_count_from_pins([p for p in pins if isinstance(p, dict)])
            if int(list_count) < 1:
                raise ValueError(f"拼装列表长度非法：{list_count}")

        for pin in pins:
            if not isinstance(pin, dict):
                continue
            if int(pin.get("kind_int") or 0) != 3:
                continue
            pin_index_int = int(pin.get("index_int") or 0)

            # 变参：只取 1..count（0 为长度），避免把未使用的预留 pins 全部写入 Graph Code
            if list_count is not None:
                if pin_index_int == 0:
                    continue
                if pin_index_int > int(list_count):
                    continue

            connects = pin.get("connects") or []
            if isinstance(connects, list) and connects:
                continue

            value = pin.get("value")
            if value is None:
                continue

            port_name = _map_data_input_index(
                node_title=title,
                node_def=resolved.node_def,
                index_int=int(pin_index_int),
                graph_ir_node=node_item,
            )
            ensure_input_port(node_model, port_name)
            node_model.input_constants[str(port_name)] = _normalize_enum_constant(
                node_def=resolved.node_def,
                port_name=str(port_name),
                value=value,
            )

    # graph variables（用于生成 GRAPH_VARIABLES，支撑获取/设置节点图变量的类型推断）
    raw_graph_variables = graph_ir.get("graph_variables")
    if raw_graph_variables is not None:
        if not isinstance(raw_graph_variables, list):
            raise TypeError("graph_ir.graph_variables must be list")
        normalized_vars: List[dict] = []
        for entry in raw_graph_variables:
            if not isinstance(entry, dict):
                continue
            name_value = str(entry.get("name") or "").strip()
            if name_value == "":
                continue
            type_expr = str(entry.get("var_type_expr") or "").strip()
            variable_type = _map_node_data_type_expr_to_type_name(type_expr)
            if variable_type == "":
                raise ValueError(f"无法识别的图变量类型表达式：name={name_value!r} var_type_expr={type_expr!r}")

            payload: dict = {
                "name": name_value,
                "variable_type": variable_type,
                "default_value": entry.get("default_value"),
                "description": "",
                "is_exposed": bool(entry.get("exposed")) if entry.get("exposed") is not None else False,
                "struct_name": "",
                "dict_key_type": "",
                "dict_value_type": "",
            }

            if variable_type == "字典":
                key_expr = str(entry.get("key_type_expr") or "").strip()
                val_expr = str(entry.get("value_type_expr") or "").strip()
                key_name = _map_node_data_type_expr_to_type_name(key_expr)
                val_name = _map_node_data_type_expr_to_type_name(val_expr)
                if key_name == "" or val_name == "":
                    raise ValueError(
                        "字典图变量缺少可识别的 KV 类型："
                        f"name={name_value!r} key_type_expr={key_expr!r} value_type_expr={val_expr!r}"
                    )
                payload["dict_key_type"] = key_name
                payload["dict_value_type"] = val_name

            if variable_type in {"结构体", "结构体列表"}:
                struct_id_int = entry.get("struct_id_int")
                if not isinstance(struct_id_int, int) or int(struct_id_int) <= 0:
                    raise ValueError(f"结构体图变量缺少 struct_id_int：name={name_value!r} struct_id_int={struct_id_int!r}")
                from engine.struct import get_default_struct_repository

                repo = get_default_struct_repository()
                struct_payload = repo.get_payload(str(int(struct_id_int)))
                if struct_payload is None:
                    raise KeyError(f"未找到结构体定义：struct_id={int(struct_id_int)}（图变量 {name_value!r}）")
                struct_name = str(struct_payload.get("struct_name") or "").strip()
                if struct_name == "":
                    raise ValueError(f"结构体定义缺少 struct_name：struct_id={int(struct_id_int)}")
                payload["struct_name"] = struct_name

            normalized_vars.append(payload)

        graph_model.graph_variables = normalized_vars

    # port_type_overrides：用 `.gia` pins 的 type_expr 作为“有效端口类型”证据，
    # 让 codegen 在生成类型注解时不必回退到节点声明的“泛型”或默认字符串。
    port_type_overrides: Dict[str, Dict[str, str]] = {}
    for node_index_int, node_model in node_model_by_node_index.items():
        node_item = node_item_by_index.get(int(node_index_int)) or {}
        pins = node_item.get("pins") or []
        if not isinstance(pins, list):
            continue
        resolved = resolved_by_node_index.get(int(node_index_int))
        if resolved is None:
            continue

        per_node: Dict[str, str] = {}
        for pin in pins:
            if not isinstance(pin, dict):
                continue
            if int(pin.get("kind_int") or 0) != 4:
                continue
            pin_index_int = int(pin.get("index_int") or 0)
            type_expr = str(pin.get("type_expr") or "").strip()
            if type_expr == "":
                continue

            type_name = _map_node_data_type_expr_to_type_name(type_expr)
            if type_name == "":
                continue

            # 字典：尽力细化为“键-值字典”别名（用于校验与写回侧 concrete 推断）
            if type_name == "字典":
                key_expr = str(pin.get("dict_key_type_expr") or "").strip()
                val_expr = str(pin.get("dict_value_type_expr") or "").strip()
                key_name = _map_node_data_type_expr_to_type_name(key_expr)
                val_name = _map_node_data_type_expr_to_type_name(val_expr)
                if key_name and val_name:
                    type_name = f"{key_name}-{val_name}字典"

            port_name = _map_data_output_index(
                node_title=str(getattr(node_model, "title", "") or ""),
                node_def=resolved.node_def,
                index_int=int(pin_index_int),
            )
            if port_name:
                per_node[str(port_name)] = str(type_name)

        if per_node:
            port_type_overrides[str(node_model.id)] = per_node

    if port_type_overrides:
        if not isinstance(graph_model.metadata, dict):
            graph_model.metadata = {}
        graph_model.metadata["port_type_overrides"] = port_type_overrides

    metadata = {
        "graph_id": graph_model.graph_id,
        "graph_name": graph_model.graph_name,
        "graph_type": graph_scope,
        "description": (
            f"导入自 .gia NodeGraph（graph_id_int={int(graph_id_int)}；source={sanitize_file_stem(str(graph_ir.get('source_gia_file') or ''))}）。"
        ),
    }
    return graph_model, metadata


__all__ = [
    "ResolvedNodeDef",
    "build_graph_model_from_graph_ir",
]

